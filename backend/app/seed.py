"""
Initialises the in-memory DB at startup from data/Input_Data.json.
The loader is tolerant of slightly different key names so the official
hackathon Input_Data.json can be dropped in (see README > "Using your own data").
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import config
from .models import (Application, AvailabilitySlot, JobDescription, Question,
                     Role, User)
from .security import hash_password
from .services.audit import audit

log = logging.getLogger("smarthire.seed")


def _get(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
    return list(v)


def ensure_master_admin(db: Session) -> None:
    admin = db.query(User).filter(User.email == config.MASTER_ADMIN_EMAIL).first()
    if admin is None:
        admin = User(full_name=config.MASTER_ADMIN_NAME, email=config.MASTER_ADMIN_EMAIL,
                     password_hash=hash_password(config.MASTER_ADMIN_PASSWORD),
                     role=Role.ADMIN, is_master=True)
        db.add(admin)
    else:
        admin.role, admin.is_master, admin.is_active = Role.ADMIN, True, True
    db.commit()


def _seed_availability(db: Session, interviewers: list[User]) -> None:
    """Give each seeded interviewer some free slots on the next 5 working days."""
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days = []
    while len(days) < 5:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days.append(day)
    patterns = [(10, 14, 16), (11, 15)]
    for i, iv in enumerate(interviewers):
        for d in days:
            for h in patterns[i % len(patterns)]:
                st = d.replace(hour=h)
                db.add(AvailabilitySlot(interviewer_id=iv.id, start=st, end=st + timedelta(hours=1)))


def load_seed(db: Session) -> None:
    ensure_master_admin(db)
    path = config.SEED_FILE
    if not path.exists():
        log.warning("Seed file %s not found — starting with an empty dataset", path)
        return
    data = json.loads(path.read_text(encoding="utf-8"))

    # ---------------- job descriptions
    jd_map: dict[str, JobDescription] = {}
    for i, raw in enumerate(_get(data, "job_descriptions", "jds", "jobs", default=[]), 1):
        w = raw.get("weights", {}) or {}
        jd = JobDescription(
            title=_get(raw, "title", "role", "name", default=f"Job {i}"),
            department=_get(raw, "department", "team", default="Engineering"),
            location=_get(raw, "location", default="Bengaluru"),
            experience=str(_get(raw, "experience", "experience_required", "years", default="0-2 years")),
            description=_get(raw, "description", "summary", "responsibilities", default=""),
            must_have_skills=_as_list(_get(raw, "must_have_skills", "required_skills", "skills", "must_have")),
            nice_to_have_skills=_as_list(_get(raw, "nice_to_have_skills", "preferred_skills", "nice_to_have")),
            ats_threshold=float(_get(raw, "ats_threshold", "threshold", default=60)),
            weight_resume=float(_get(w, "resume", default=0.4)),
            weight_assessment=float(_get(w, "assessment", "qa", default=0.3)),
            weight_interview=float(_get(w, "interview", default=0.3)),
            pass_threshold=float(_get(raw, "pass_threshold", default=70)),
            hold_threshold=float(_get(raw, "hold_threshold", default=50)),
            confidence_cutoff=float(_get(raw, "confidence_cutoff", default=0.6)),
            num_questions=int(_get(raw, "num_questions", default=5)),
        )
        db.add(jd)
        db.flush()
        key = str(_get(raw, "id", "jd_id", default=i))
        jd_map[key] = jd
        jd_map[jd.title.lower()] = jd
        jd_map[str(i)] = jd

    def find_jd(ref) -> JobDescription | None:
        if ref is None:
            return None
        return jd_map.get(str(ref)) or jd_map.get(str(ref).lower())

    # ---------------- questions
    for raw in _get(data, "questions", "technical_questions", default=[]):
        jd = find_jd(_get(raw, "jd_id", "jd", "job_id", "role"))
        if not jd:
            continue
        rubric = []
        for r in _as_list(_get(raw, "rubric", "rubric_points", "expected_points", default=[])):
            rubric.append(r if isinstance(r, dict) else {"point": str(r)})
        db.add(Question(jd_id=jd.id, text=_get(raw, "question", "text", "prompt"),
                        rubric=rubric, difficulty=_get(raw, "difficulty", default="medium"),
                        time_limit_sec=int(_get(raw, "time_limit_sec", "time_limit", "timer", default=120))))

    # ---------------- users
    users_by_email: dict[str, User] = {}
    users_by_id: dict[str, User] = {}
    interviewers = []
    hash_cache: dict[str, str] = {}  # seed users often share passwords; bcrypt is slow

    def hashed(pw: str) -> str:
        if pw not in hash_cache:
            hash_cache[pw] = hash_password(pw)
        return hash_cache[pw]

    for raw in _get(data, "users", default=[]):
        role = str(_get(raw, "role", default="candidate")).lower()
        role = {"hiring_manager": "admin", "hr": "admin", "recruiter": "interviewer"}.get(role, role)
        if role not in Role.ALL:
            continue
        if role == Role.ADMIN and not config.SEED_JSON_ADMINS:
            log.info("Skipping seed admin %s (single master admin mode)", raw.get("email"))
            continue
        email = str(_get(raw, "email", "username")).lower()
        if db.query(User).filter(User.email == email).first():
            continue
        u = User(full_name=_get(raw, "name", "full_name", default=email.split("@")[0]),
                 email=email, mobile=_get(raw, "mobile", "phone"),
                 password_hash=hashed(str(_get(raw, "password", default="Password@123"))),
                 role=role, designation=_get(raw, "designation", "title"))
        db.add(u)
        db.flush()
        users_by_email[email] = u
        if _get(raw, "id") is not None:
            users_by_id[str(raw["id"])] = u
        if role == Role.INTERVIEWER:
            interviewers.append(u)

    # ---------------- resumes -> candidate profile + application (unscored)
    for raw in _get(data, "resumes", default=[]):
        ref = _get(raw, "candidate_email", "email")
        cand = users_by_email.get(str(ref).lower()) if ref else None
        if cand is None:
            cand = users_by_id.get(str(_get(raw, "candidate_id", "user_id", default="")))
        if cand is None:
            name = _get(raw, "name", "candidate_name")
            cand = next((u for u in users_by_email.values() if name and u.full_name == name), None)
        if cand is None:
            continue
        text = _get(raw, "resume_text", "text", "content", "resume", default="")
        cand.resume_text, cand.resume_filename = text, f"{cand.full_name.replace(' ', '_')}_resume.txt"
        cand.resume_updated_at = datetime.now()
        jd = find_jd(_get(raw, "jd_id", "applied_jd", "applied_for", "role"))
        if jd:
            db.add(Application(candidate_id=cand.id, jd_id=jd.id, resume_snapshot=text))

    _seed_availability(db, interviewers)
    audit(db, None, "SEED_LOADED", "system", None,
          f"{len(set(jd_map.values()))} JDs, {len(users_by_email)} users from {path.name}")
    db.commit()
    log.info("Seeded %s JDs and %s users", len(set(jd_map.values())), len(users_by_email))
