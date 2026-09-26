"""Hiring Manager (Admin) APIs — every route requires role=admin (JWT)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm import llm_client
from ..models import (Application, AuditLog, AvailabilitySlot, JobDescription,
                      Note, Question, Role, Status, User, now)
from ..schemas import (DecisionIn, InterviewerIn, InterviewerUpdate, JDIn,
                       QuestionIn, ReviewIn, ScheduleIn, TextIn)
from ..security import hash_password, require_admin
from ..services import scheduler
from ..services.audit import audit, notify
from ..services.scoring import (PRE_ASSESSMENT, fuse, notify_candidate,
                                score_application_resume, start_batch)
from ..services.views import (app_detail, app_summary, iso, jd_view,
                              question_view, user_view)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _app(db: Session, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    return app


# ================================================================ dashboard
@router.get("/stats")
def stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    apps = db.query(Application).all()
    by = lambda *s: sum(1 for a in apps if a.status in s)
    return {
        "total_applications": len(apps),
        "in_screening": by(Status.APPLIED, Status.SCREENING, Status.ASSESSMENT_IN_PROGRESS,
                           Status.ASSESSMENT_SUBMITTED),
        "awaiting_review": by(Status.ASSESSMENT_SUBMITTED),
        "in_interview": by(Status.INTERVIEW_PENDING, Status.INTERVIEW_SCHEDULED, Status.INTERVIEW_COMPLETED),
        "awaiting_decision": by(Status.INTERVIEW_COMPLETED),
        "offers": by(Status.OFFERED, Status.OFFER_ACCEPTED),
        "accepted_offers": by(Status.OFFER_ACCEPTED),
        "filtered": by(Status.FILTERED),
        "rejected": by(Status.REJECTED),
        "flagged": sum(1 for a in apps if a.flags),
        "candidates": db.query(User).filter(User.role == Role.CANDIDATE).count(),
        "interviewers": db.query(User).filter(User.role == Role.INTERVIEWER, User.is_active.is_(True)).count(),
        "jobs": db.query(JobDescription).count(),
        "llm_provider": llm_client.provider_label(),
        "by_status": {s: by(s) for s in sorted({a.status for a in apps})},
    }


# ================================================================ interviewers
@router.get("/interviewers")
def list_interviewers(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    out = []
    for u in db.query(User).filter(User.role == Role.INTERVIEWER).order_by(User.id):
        d = user_view(u)
        d["assigned"] = db.query(Application).filter(Application.interviewer_id == u.id).count()
        d["free_slots"] = db.query(AvailabilitySlot).filter(
            AvailabilitySlot.interviewer_id == u.id, AvailabilitySlot.is_booked.is_(False),
            AvailabilitySlot.start >= datetime.now()).count()
        out.append(d)
    return out


@router.post("/interviewers", status_code=201)
def create_interviewer(body: InterviewerIn, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "A user with this email already exists")
    if body.mobile and db.query(User).filter(User.mobile == body.mobile).first():
        raise HTTPException(409, "A user with this mobile number already exists")
    u = User(full_name=body.full_name.strip(), email=email, mobile=body.mobile or None,
             designation=body.designation, password_hash=hash_password(body.password),
             role=Role.INTERVIEWER, created_by=admin.id)
    db.add(u)
    db.flush()
    audit(db, admin, "INTERVIEWER_CREATED", "user", u.id, f"{u.full_name} <{email}>")
    db.commit()
    notify(email, "Your SmartHire interviewer account is ready", "Credentials shared by admin")
    return user_view(u)


@router.patch("/interviewers/{uid}")
def update_interviewer(uid: int, body: InterviewerUpdate, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u or u.role != Role.INTERVIEWER:
        raise HTTPException(404, "Interviewer not found")
    if body.mobile and body.mobile != u.mobile and db.query(User).filter(User.mobile == body.mobile).first():
        raise HTTPException(409, "Mobile number already in use")
    changes = []
    for field in ("full_name", "mobile", "designation", "is_active"):
        val = getattr(body, field)
        if val is not None:
            setattr(u, field, val or None if field == "mobile" else val)
            changes.append(field)
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(422, "Password must be at least 6 characters")
        u.password_hash = hash_password(body.password)
        changes.append("password")
    audit(db, admin, "INTERVIEWER_UPDATED", "user", u.id, ", ".join(changes))
    db.commit()
    return user_view(u)


@router.delete("/interviewers/{uid}")
def delete_interviewer(uid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u or u.role != Role.INTERVIEWER:
        raise HTTPException(404, "Interviewer not found")
    if db.query(Application).filter(Application.interviewer_id == uid).count():
        u.is_active = False
        audit(db, admin, "INTERVIEWER_DEACTIVATED", "user", uid, "Has interview history; deactivated")
        db.commit()
        return {"message": "Interviewer has interview history, so the account was deactivated instead."}
    db.query(AvailabilitySlot).filter(AvailabilitySlot.interviewer_id == uid).delete()
    db.delete(u)
    audit(db, admin, "INTERVIEWER_DELETED", "user", uid, u.email)
    db.commit()
    return {"message": "Interviewer deleted"}


# ================================================================ candidates (read-only)
@router.get("/candidates")
def list_candidates(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    out = []
    for u in db.query(User).filter(User.role == Role.CANDIDATE).order_by(User.created_at.desc(), User.id.desc()):
        d = user_view(u)
        apps = db.query(Application).filter(Application.candidate_id == u.id).all()
        d["applications"] = [{"id": a.id, "jd_title": a.jd.title, "status": a.status} for a in apps]
        out.append(d)
    return out


@router.get("/candidates/{uid}")
def candidate_profile(uid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u or u.role != Role.CANDIDATE:
        raise HTTPException(404, "Candidate not found")
    d = user_view(u)
    d["resume_text"] = u.resume_text
    d["resume_filename"] = u.resume_filename
    d["applications"] = [app_summary(a) for a in
                         db.query(Application).filter(Application.candidate_id == uid)]
    return d


# ================================================================ job descriptions
@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    out = []
    for jd in db.query(JobDescription).order_by(JobDescription.id):
        d = jd_view(jd, admin=True)
        apps = db.query(Application).filter(Application.jd_id == jd.id).all()
        d["applications"] = len(apps)
        d["unscored"] = sum(1 for a in apps if a.status == Status.APPLIED)
        out.append(d)
    return out


@router.post("/jobs", status_code=201)
def create_job(body: JDIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    jd = JobDescription(**body.model_dump())
    db.add(jd)
    db.flush()
    audit(db, admin, "JD_CREATED", "jd", jd.id, jd.title)
    db.commit()
    return jd_view(jd, admin=True)


@router.get("/jobs/{jd_id}")
def get_job(jd_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    jd = db.get(JobDescription, jd_id) or _404("Job not found")
    d = jd_view(jd, admin=True)
    d["questions"] = [question_view(q) for q in jd.questions]
    return d


@router.put("/jobs/{jd_id}")
def update_job(jd_id: int, body: JDIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    jd = db.get(JobDescription, jd_id) or _404("Job not found")
    for k, v in body.model_dump().items():
        setattr(jd, k, v)
    # weights/thresholds changed -> re-fuse every application of this JD
    for a in db.query(Application).filter(Application.jd_id == jd_id):
        fuse(a)
    audit(db, admin, "JD_UPDATED", "jd", jd.id,
          f"ATS {jd.ats_threshold}, weights {jd.weight_resume}/{jd.weight_assessment}/{jd.weight_interview}, "
          f"pass {jd.pass_threshold}, hold {jd.hold_threshold}, conf {jd.confidence_cutoff}")
    db.commit()
    return jd_view(jd, admin=True)


@router.delete("/jobs/{jd_id}")
def delete_job(jd_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    jd = db.get(JobDescription, jd_id) or _404("Job not found")
    if db.query(Application).filter(Application.jd_id == jd_id).count():
        jd.is_active = False
        msg = "Job has applications, so it was closed (hidden from candidates) instead of deleted."
    else:
        db.delete(jd)
        msg = "Job deleted"
    audit(db, admin, "JD_DELETED", "jd", jd_id, msg)
    db.commit()
    return {"message": msg}


@router.post("/jobs/{jd_id}/batch-score")
def batch_score(jd_id: int, force: bool = False, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    """Triggered automatically when admin selects a JD. force=true re-scores everyone
    who hasn't started the assessment (e.g. after threshold changes)."""
    jd = db.get(JobDescription, jd_id) or _404("Job not found")
    if jd.batch_status == "running":
        return {"message": "Batch already running", "status": "running"}
    apps = db.query(Application).filter(Application.jd_id == jd_id).all()
    todo = [a for a in apps if (a.status == Status.APPLIED) or
            (force and a.status in PRE_ASSESSMENT and a.assessment_started_at is None)]
    if not todo:
        return {"message": "Nothing to score", "status": jd.batch_status}
    audit(db, admin, "BATCH_STARTED", "jd", jd.id, f"{len(todo)} resumes queued (force={force})")
    jd.batch_status, jd.batch_total, jd.batch_done = "running", len(todo), 0
    db.commit()
    start_batch(jd_id, [a.id for a in todo])
    return {"message": f"Scoring {len(todo)} resumes", "status": "running"}


@router.get("/jobs/{jd_id}/batch-status")
def batch_status(jd_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    jd = db.get(JobDescription, jd_id) or _404("Job not found")
    db.refresh(jd)
    return {"status": jd.batch_status, "total": jd.batch_total, "done": jd.batch_done,
            "finished_at": iso(jd.batch_finished_at)}


# ---------------------------------------------------------------- questions
@router.get("/jobs/{jd_id}/questions")
def list_questions(jd_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [question_view(q) for q in db.query(Question).filter(Question.jd_id == jd_id)]


@router.post("/jobs/{jd_id}/questions", status_code=201)
def add_question(jd_id: int, body: QuestionIn, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    db.get(JobDescription, jd_id) or _404("Job not found")
    q = Question(jd_id=jd_id, text=body.text, difficulty=body.difficulty,
                 time_limit_sec=body.time_limit_sec, rubric=[{"point": r} for r in body.rubric if r.strip()])
    db.add(q)
    db.flush()
    audit(db, admin, "QUESTION_ADDED", "question", q.id, body.text[:80])
    db.commit()
    return question_view(q)


@router.put("/questions/{qid}")
def update_question(qid: int, body: QuestionIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    q = db.get(Question, qid) or _404("Question not found")
    q.text, q.difficulty, q.time_limit_sec = body.text, body.difficulty, body.time_limit_sec
    q.rubric = [{"point": r} for r in body.rubric if r.strip()]
    audit(db, admin, "QUESTION_UPDATED", "question", q.id, body.text[:80])
    db.commit()
    return question_view(q)


@router.delete("/questions/{qid}")
def delete_question(qid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    q = db.get(Question, qid) or _404("Question not found")
    from ..models import AssessmentAnswer
    if db.query(AssessmentAnswer).filter(AssessmentAnswer.question_id == qid).count():
        raise HTTPException(409, "Question already used in an assessment; edit it instead")
    db.delete(q)
    audit(db, admin, "QUESTION_DELETED", "question", qid, "")
    db.commit()
    return {"message": "Question deleted"}


# ================================================================ applications
@router.get("/applications")
def list_applications(jd_id: int | None = None, status: str | None = None, band: str | None = None,
                      flagged: bool | None = None, q: str | None = None,
                      db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    query = db.query(Application)
    if jd_id:
        query = query.filter(Application.jd_id == jd_id)
    if status:
        query = query.filter(Application.status.in_(status.split(",")))
    if band:
        query = query.filter(Application.band == band)
    rows = [app_summary(a) for a in query.order_by(Application.id)]
    if flagged is not None:
        rows = [r for r in rows if bool(r["flags"]) == flagged]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["candidate_name"].lower() or ql in r["candidate_email"].lower()]
    return rows


@router.get("/applications/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = _app(db, app_id)
    db.refresh(a)
    return app_detail(a)


@router.post("/applications/{app_id}/rescore")
def rescore(app_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = _app(db, app_id)
    if a.status not in PRE_ASSESSMENT or a.assessment_started_at:
        raise HTTPException(409, "Resume can only be re-scored before the assessment starts")
    score_application_resume(db, a, admin)
    db.commit()
    return app_detail(a)


@router.post("/applications/{app_id}/review")
def review(app_id: int, body: ReviewIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin decision after the online assessment (or manual ATS override)."""
    a = _app(db, app_id)
    if body.action == "PROMOTE":
        if a.status not in (Status.FILTERED, Status.APPLIED):
            raise HTTPException(409, "Only filtered/unscored applications can be promoted")
        a.status, a.archive_reason = Status.SCREENING, None
        notify_candidate(a, "You have been shortlisted for the online assessment")
    else:
        allowed = (Status.ASSESSMENT_SUBMITTED, Status.ON_HOLD, Status.SCREENING)
        if a.status not in allowed:
            raise HTTPException(409, f"Cannot review an application in status {a.status}")
        if body.action == "APPROVE":
            if a.status == Status.SCREENING:
                raise HTTPException(409, "Candidate has not completed the assessment yet")
            a.status = Status.INTERVIEW_PENDING
            notify_candidate(a, "You are shortlisted for the interview round")
        elif body.action == "REJECT":
            a.status, a.final_decision, a.decided_at = Status.REJECTED, "REJECT", now()
            notify_candidate(a, "Application update")
        else:
            a.status = Status.ON_HOLD
            notify_candidate(a, "Application on hold")
    if body.note:
        db.add(Note(application_id=a.id, author_id=admin.id, text=body.note))
    audit(db, admin, f"REVIEW_{body.action}", "application", a.id, f"{a.candidate.full_name} -> {a.status}")
    db.commit()
    return app_detail(a)


@router.post("/applications/{app_id}/schedule")
def schedule(app_id: int, body: ScheduleIn, db: Session = Depends(get_db),
             admin: User = Depends(require_admin)):
    a = _app(db, app_id)
    if a.status not in (Status.INTERVIEW_PENDING, Status.INTERVIEW_SCHEDULED):
        raise HTTPException(409, "Candidate must be approved for interview first")
    iv = db.get(User, body.interviewer_id)
    if not iv or iv.role != Role.INTERVIEWER or not iv.is_active:
        raise HTTPException(404, "Interviewer not found or inactive")
    if body.slot_id:
        slot = db.get(AvailabilitySlot, body.slot_id)
        if not slot or slot.interviewer_id != iv.id:
            raise HTTPException(404, "Slot not found for this interviewer")
        if slot.is_booked and slot.application_id != a.id:
            raise HTTPException(409, "Slot already booked")
    elif body.start:
        start = body.start.replace(tzinfo=None, second=0, microsecond=0)
        slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.interviewer_id == iv.id,
                                                 AvailabilitySlot.start == start).first()
        if slot and slot.is_booked and slot.application_id != a.id:
            raise HTTPException(409, "Interviewer already has an interview at that time")
        if not slot:
            slot = AvailabilitySlot(interviewer_id=iv.id, start=start, end=start + timedelta(hours=1))
            db.add(slot)
            db.flush()
    else:
        raise HTTPException(422, "Choose an availability slot or a custom date/time")
    scheduler.book(db, a, slot, admin, "manual")
    db.commit()
    return app_detail(a)


@router.post("/applications/{app_id}/next-steps")
def next_steps(app_id: int, body: TextIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = _app(db, app_id)
    a.next_steps = body.text
    audit(db, admin, "NEXT_STEPS", "application", a.id, body.text[:120])
    db.commit()
    return {"next_steps": a.next_steps}


@router.post("/applications/{app_id}/notes")
def add_note(app_id: int, body: TextIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = _app(db, app_id)
    db.add(Note(application_id=a.id, author_id=admin.id, text=body.text))
    audit(db, admin, "NOTE_ADDED", "application", a.id, body.text[:120])
    db.commit()
    return app_detail(a)


@router.post("/applications/{app_id}/decision")
def final_decision(app_id: int, body: DecisionIn, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    a = _app(db, app_id)
    if a.status not in (Status.INTERVIEW_COMPLETED, Status.ON_HOLD, Status.INTERVIEW_SCHEDULED):
        raise HTTPException(409, "Final decision is available after the interview")
    a.final_decision, a.decided_at = body.decision, now()
    a.status = {"OFFER": Status.OFFERED, "REJECT": Status.REJECTED, "HOLD": Status.ON_HOLD}[body.decision]
    if body.note:
        db.add(Note(application_id=a.id, author_id=admin.id, text=body.note))
    audit(db, admin, f"FINAL_{body.decision}", "application", a.id,
          f"{a.candidate.full_name} ({a.jd.title}) combined={a.combined_score}")
    notify_candidate(a, "Final decision released" if body.decision != "HOLD" else "Application on hold")
    db.commit()
    return app_detail(a)


# ================================================================ scheduling
@router.post("/schedule/auto")
def run_auto_schedule(jd_id: int | None = None, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    result = scheduler.auto_schedule(db, admin, jd_id)
    db.commit()
    return result


@router.get("/schedule")
def schedule_overview(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    slots = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.start >= datetime.now() - timedelta(days=1)).order_by(AvailabilitySlot.start).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.role == Role.INTERVIEWER)}
    pending = db.query(Application).filter(Application.status == Status.INTERVIEW_PENDING).all()
    interviews = db.query(Application).filter(Application.interview_at.isnot(None)).order_by(Application.interview_at).all()
    return {
        "slots": [{"id": s.id, "interviewer_id": s.interviewer_id,
                   "interviewer": names.get(s.interviewer_id, "?"), "start": iso(s.start),
                   "end": iso(s.end), "is_booked": s.is_booked, "application_id": s.application_id}
                  for s in slots],
        "pending": [app_summary(a) for a in pending],
        "interviews": [app_summary(a) for a in interviews],
    }


# ================================================================ audit
@router.get("/audit-logs")
def audit_logs(limit: int = Query(200, le=1000), action: str | None = None, entity: str | None = None,
               db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.contains(action.upper()))
    if entity:
        q = q.filter(AuditLog.entity == entity)
    return [{"id": l.id, "actor": l.actor_name, "role": l.actor_role, "action": l.action,
             "entity": l.entity, "entity_id": l.entity_id, "details": l.details,
             "created_at": iso(l.created_at)} for l in q.order_by(AuditLog.id.desc()).limit(limit)]


def _404(msg: str):
    raise HTTPException(404, msg)
