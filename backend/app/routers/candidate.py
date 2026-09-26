"""Candidate APIs. Responses NEVER include AI scores, justifications or flags."""
import random

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import MAX_RESUME_CHARS
from ..database import get_db
from ..models import (Application, AssessmentAnswer, JobDescription, Status,
                      User, now)
from ..schemas import AnswerIn, OfferResponseIn, ResumeTextIn, TelemetryIn
from ..security import require_candidate
from ..services.audit import audit, notify
from ..services.scoring import (fuse, score_application_resume,
                                start_assessment_scoring)
from ..services.views import candidate_app_view, iso, jd_view, match_priority

router = APIRouter(prefix="/api/candidate", tags=["candidate"])

GRACE_SEC = 5
PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, None: 3}


def _my_app(db: Session, app_id: int, me: User) -> Application:
    a = db.get(Application, app_id)
    if not a or a.candidate_id != me.id:
        raise HTTPException(404, "Application not found")
    return a


# ---------------------------------------------------------------- profile & resume
@router.get("/profile")
def profile(me: User = Depends(require_candidate)):
    return {"id": me.id, "full_name": me.full_name, "email": me.email, "mobile": me.mobile,
            "resume_text": me.resume_text, "resume_filename": me.resume_filename,
            "resume_updated_at": iso(me.resume_updated_at)}


def _save_resume(db: Session, me: User, text: str, filename: str | None):
    text = text.replace("\x00", "").strip()
    if len(text) < 30:
        raise HTTPException(422, "Resume text is too short")
    me.resume_text = text[:MAX_RESUME_CHARS]
    me.resume_filename = filename or "resume.txt"
    me.resume_updated_at = now()
    audit(db, me, "RESUME_UPLOADED", "user", me.id, me.resume_filename)
    db.commit()
    return {"message": "Resume saved", "resume_filename": me.resume_filename,
            "resume_updated_at": iso(me.resume_updated_at)}


@router.post("/resume")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db),
                        me: User = Depends(require_candidate)):
    name = (file.filename or "").lower()
    if not name.endswith((".txt", ".md")):
        raise HTTPException(415, "Please upload a plain-text resume (.txt / .md) or paste the text")
    raw = await file.read()
    if len(raw) > 500_000:
        raise HTTPException(413, "File too large (max 500 KB)")
    return _save_resume(db, me, raw.decode("utf-8", errors="ignore"), file.filename)


@router.post("/resume/text")
def paste_resume(body: ResumeTextIn, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    return _save_resume(db, me, body.text, body.filename or "pasted-resume.txt")


# ---------------------------------------------------------------- jobs
@router.get("/jobs")
def jobs(db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    applied = {a.jd_id: a.id for a in db.query(Application).filter(Application.candidate_id == me.id)}
    out = []
    for jd in db.query(JobDescription).filter(JobDescription.is_active.is_(True)):
        d = jd_view(jd)
        d["priority"] = match_priority(jd, me.resume_text)
        d["applied"] = jd.id in applied
        d["application_id"] = applied.get(jd.id)
        out.append(d)
    out.sort(key=lambda d: (PRIORITY_ORDER[d["priority"]], d["id"]))
    return out


@router.post("/jobs/{jd_id}/apply", status_code=201)
def apply(jd_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    jd = db.get(JobDescription, jd_id)
    if not jd or not jd.is_active:
        raise HTTPException(404, "Job not found")
    if not me.resume_text:
        raise HTTPException(400, "Please upload your resume before applying")
    if db.query(Application).filter(Application.candidate_id == me.id, Application.jd_id == jd_id).first():
        raise HTTPException(409, "You have already applied for this role")
    a = Application(candidate_id=me.id, jd_id=jd_id, resume_snapshot=me.resume_text)
    db.add(a)
    db.flush()
    db.refresh(a)
    audit(db, me, "APPLIED", "application", a.id, jd.title)
    score_application_resume(db, a)  # AI ATS score — kept hidden from the candidate
    db.commit()
    passed = a.status == Status.SCREENING
    notify(me.email, "Application received", f"{jd.title}: {'shortlisted' if passed else 'not shortlisted'}")
    return {
        "passed": passed,
        "message": ("Congratulations! You have cleared the initial screening. "
                    "The online assessment is now unlocked." if passed else
                    "Thank you for applying. Unfortunately your profile did not clear "
                    "the initial screening for this role."),
        "application": candidate_app_view(a),
    }


# ---------------------------------------------------------------- applications
@router.get("/applications")
def my_applications(db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    apps = db.query(Application).filter(Application.candidate_id == me.id).order_by(Application.created_at.desc())
    return [candidate_app_view(a) for a in apps]


@router.get("/applications/{app_id}")
def my_application(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    db.refresh(a)
    return candidate_app_view(a)


@router.post("/applications/{app_id}/offer-response")
def offer_response(app_id: int, body: OfferResponseIn, db: Session = Depends(get_db),
                   me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    if a.status != Status.OFFERED:
        raise HTTPException(409, "There is no open offer for this application")
    a.candidate_response, a.responded_at = body.response, now()
    a.status = Status.OFFER_ACCEPTED if body.response == "ACCEPTED" else Status.OFFER_DECLINED
    audit(db, me, f"OFFER_{body.response}", "application", a.id, a.jd.title)
    notify("admin", f"{me.full_name} {body.response.lower()} the offer for {a.jd.title}")
    db.commit()
    return candidate_app_view(a)


@router.get("/applications/{app_id}/offer-letter")
def offer_letter(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    if a.status not in (Status.OFFERED, Status.OFFER_ACCEPTED):
        raise HTTPException(404, "No offer letter available")
    return {"candidate": me.full_name, "email": me.email, "role": a.jd.title,
            "department": a.jd.department, "location": a.jd.location,
            "issued_on": iso(a.decided_at), "status": a.status, "reference": f"SH-{a.id:05d}"}


# ---------------------------------------------------------------- online assessment
def _question_payload(ans: AssessmentAnswer, total: int) -> dict:
    elapsed = int((now() - ans.served_at).total_seconds()) if ans.served_at else 0
    limit = ans.question.time_limit_sec
    return {"answer_id": ans.id, "index": ans.order + 1, "total": total,
            "text": ans.question.text, "time_limit_sec": limit,
            "remaining_sec": max(0, limit - elapsed), "difficulty": ans.question.difficulty}


def _next(db: Session, a: Application) -> dict:
    pending = [x for x in a.answers if x.submitted_at is None]
    total = len(a.answers)
    if not pending:
        return {"done": True, "total": total, "answered": total}
    cur = pending[0]
    if cur.served_at is None:  # server-side timer starts when question is first served
        cur.served_at = now()
        db.commit()
    return {"done": False, "total": total, "answered": total - len(pending),
            "question": _question_payload(cur, total)}


def _finish(db: Session, a: Application) -> None:
    for x in a.answers:
        if x.submitted_at is None:
            x.submitted_at, x.answer_text, x.timed_out = now(), x.answer_text or "", True
    a.status = Status.ASSESSMENT_SUBMITTED
    a.assessment_submitted_at = now()
    a.assessment_scoring = "pending"
    audit(db, a.candidate, "ASSESSMENT_SUBMITTED", "application", a.id, a.jd.title)
    db.commit()
    notify(a.candidate.email, "Assessment submitted", "We'll update you soon")
    start_assessment_scoring(a.id)


@router.get("/applications/{app_id}/assessment")
def assessment_info(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    qs = a.jd.questions[: a.jd.num_questions]
    return {"application_id": a.id, "jd_title": a.jd.title, "status": a.status,
            "num_questions": len(a.answers) or len(qs),
            "total_time_sec": sum(q.time_limit_sec for q in qs),
            "started": a.assessment_started_at is not None,
            "can_start": a.status in (Status.SCREENING, Status.ASSESSMENT_IN_PROGRESS),
            "rules": [
                "The assessment runs in full-screen mode. Exiting full screen is recorded.",
                "Switching tabs or windows is not allowed and every switch is recorded.",
                "Copy, paste and right-click are disabled.",
                "Questions are shown one at a time. You cannot go back.",
                "Each question has its own timer. When it runs out, your answer is auto-submitted.",
                "Refreshing the page does not reset the timer.",
            ]}


@router.post("/applications/{app_id}/assessment/start")
def assessment_start(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    if a.status not in (Status.SCREENING, Status.ASSESSMENT_IN_PROGRESS):
        raise HTTPException(409, "Assessment is not available for this application")
    if not a.answers:
        qs = list(a.jd.questions)
        if not qs:
            raise HTTPException(409, "No questions configured for this role yet. Please try later.")
        chosen = qs if len(qs) <= a.jd.num_questions else random.sample(qs, a.jd.num_questions)
        for i, q in enumerate(chosen):
            db.add(AssessmentAnswer(application_id=a.id, question_id=q.id, order=i))
        a.status = Status.ASSESSMENT_IN_PROGRESS
        a.assessment_started_at = now()
        audit(db, me, "ASSESSMENT_STARTED", "application", a.id, a.jd.title)
        db.commit()
        db.refresh(a)
    return _next(db, a)


@router.get("/applications/{app_id}/assessment/next")
def assessment_next(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    if a.status != Status.ASSESSMENT_IN_PROGRESS:
        return {"done": True}
    return _next(db, a)


@router.post("/applications/{app_id}/assessment/answer")
def assessment_answer(app_id: int, body: AnswerIn, db: Session = Depends(get_db),
                      me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    if a.status != Status.ASSESSMENT_IN_PROGRESS:
        raise HTTPException(409, "Assessment is not in progress")
    pending = [x for x in a.answers if x.submitted_at is None]
    if not pending or pending[0].id != body.answer_id:
        raise HTTPException(409, "This question is no longer active")
    cur = pending[0]
    served = cur.served_at or now()
    elapsed = int((now() - served).total_seconds())
    cur.answer_text = (body.answer or "")[:5000]
    cur.time_taken_sec = min(elapsed, cur.question.time_limit_sec + GRACE_SEC)
    cur.timed_out = body.timed_out or elapsed > cur.question.time_limit_sec + GRACE_SEC
    cur.submitted_at = now()
    db.commit()
    if len(pending) == 1:
        _finish(db, a)
        return {"done": True, "message": "Assessment submitted. Please wait for an update."}
    return _next(db, a)


@router.post("/applications/{app_id}/assessment/submit")
def assessment_submit(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_candidate)):
    a = _my_app(db, app_id, me)
    if a.status != Status.ASSESSMENT_IN_PROGRESS:
        raise HTTPException(409, "Assessment is not in progress")
    _finish(db, a)
    return {"done": True, "message": "Assessment submitted. Please wait for an update."}


@router.post("/applications/{app_id}/assessment/telemetry")
def telemetry(app_id: int, body: TelemetryIn, db: Session = Depends(get_db),
              me: User = Depends(require_candidate)):
    """Anti-cheat events. Stored for the admin only; nothing is echoed back."""
    a = _my_app(db, app_id, me)
    if a.status != Status.ASSESSMENT_IN_PROGRESS:
        return {"ok": True}
    field = {"tab_switch": "tab_switches", "blur": "tab_switches", "paste": "paste_events",
             "copy": "copy_events", "fullscreen_exit": "fullscreen_exits"}.get(body.event)
    if field:
        setattr(a, field, (getattr(a, field) or 0) + 1)
    current = next((x for x in a.answers if x.submitted_at is None), None)
    a.telemetry_log = (a.telemetry_log or []) + [{
        "event": body.event, "at": iso(now()), "question": current.order + 1 if current else None,
        "detail": (body.detail or "")[:100]}]
    fuse(a)
    db.commit()
    return {"ok": True}
