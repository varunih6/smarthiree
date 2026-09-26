"""Interviewer APIs — only the logged-in interviewer's own slots & candidates."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Application, AvailabilitySlot, Evaluation, Note, Status,
                      User)
from ..schemas import EvaluationIn, SlotsIn, StatusIn, TextIn
from ..security import require_interviewer
from ..services.audit import audit
from ..services.scoring import fuse
from ..services.views import app_detail, app_summary, evaluation_view, iso

router = APIRouter(prefix="/api/interviewer", tags=["interviewer"])


def _mine(db: Session, app_id: int, me: User) -> Application:
    a = db.get(Application, app_id)
    if not a or a.interviewer_id != me.id:  # never leak other interviewers' candidates
        raise HTTPException(404, "Interview not found")
    return a


# ---------------------------------------------------------------- availability
@router.get("/availability")
def my_slots(db: Session = Depends(get_db), me: User = Depends(require_interviewer)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.interviewer_id == me.id,
                                              AvailabilitySlot.start >= today).order_by(AvailabilitySlot.start)
    return [{"id": s.id, "start": iso(s.start), "end": iso(s.end), "is_booked": s.is_booked,
             "application_id": s.application_id} for s in slots]


@router.post("/availability")
def add_slots(body: SlotsIn, db: Session = Depends(get_db), me: User = Depends(require_interviewer)):
    added = 0
    for st in body.starts:
        st = st.replace(tzinfo=None, second=0, microsecond=0)
        if st < datetime.now():
            continue
        exists = db.query(AvailabilitySlot).filter(AvailabilitySlot.interviewer_id == me.id,
                                                   AvailabilitySlot.start == st).first()
        if exists:
            continue
        db.add(AvailabilitySlot(interviewer_id=me.id, start=st, end=st + timedelta(minutes=body.duration_min)))
        added += 1
    audit(db, me, "AVAILABILITY_ADDED", "slot", None, f"{added} slot(s)")
    db.commit()
    return {"added": added}


@router.delete("/availability/{slot_id}")
def remove_slot(slot_id: int, db: Session = Depends(get_db), me: User = Depends(require_interviewer)):
    s = db.get(AvailabilitySlot, slot_id)
    if not s or s.interviewer_id != me.id:
        raise HTTPException(404, "Slot not found")
    if s.is_booked:
        raise HTTPException(409, "This slot already has an interview booked")
    db.delete(s)
    audit(db, me, "AVAILABILITY_REMOVED", "slot", slot_id, f"{s.start}")
    db.commit()
    return {"message": "Slot removed"}


# ---------------------------------------------------------------- interviews
@router.get("/interviews")
def my_interviews(db: Session = Depends(get_db), me: User = Depends(require_interviewer)):
    apps = db.query(Application).filter(Application.interviewer_id == me.id).order_by(Application.interview_at)
    rows = []
    for a in apps:
        r = app_summary(a)
        r["evaluated"] = any(e.interviewer_id == me.id for e in a.evaluations)
        rows.append(r)
    return rows


@router.get("/interviews/{app_id}")
def interview_detail(app_id: int, db: Session = Depends(get_db), me: User = Depends(require_interviewer)):
    a = _mine(db, app_id, me)
    db.refresh(a)
    return app_detail(a, for_interviewer=True)


@router.post("/interviews/{app_id}/evaluation")
def submit_evaluation(app_id: int, body: EvaluationIn, db: Session = Depends(get_db),
                      me: User = Depends(require_interviewer)):
    a = _mine(db, app_id, me)
    if a.status not in (Status.INTERVIEW_SCHEDULED, Status.INTERVIEW_COMPLETED):
        raise HTTPException(409, "Evaluation can only be submitted for a scheduled interview")
    ev = next((e for e in a.evaluations if e.interviewer_id == me.id), None)
    if ev is None:
        ev = Evaluation(application_id=a.id, interviewer_id=me.id, **body.model_dump())
        db.add(ev)
        a.evaluations.append(ev)
    else:
        for k, v in body.model_dump().items():
            setattr(ev, k, v)
    avg = (body.technical + body.problem_solving + body.projects + body.communication + body.overall) / 5
    a.interview_score = None if body.decision == "No-Show" else round(avg / 5 * 100, 1)
    a.interviewer_decision = body.decision
    a.status = Status.INTERVIEW_COMPLETED
    fuse(a)
    audit(db, me, "EVALUATION_SUBMITTED", "application", a.id,
          f"{a.candidate.full_name}: avg {avg:.1f}/5, {body.decision}")
    db.commit()
    return evaluation_view(ev)


@router.post("/interviews/{app_id}/status")
def set_status(app_id: int, body: StatusIn, db: Session = Depends(get_db),
               me: User = Depends(require_interviewer)):
    a = _mine(db, app_id, me)
    if a.status not in (Status.INTERVIEW_SCHEDULED, Status.INTERVIEW_COMPLETED):
        raise HTTPException(409, "Interview is not active")
    a.interviewer_decision = body.decision
    if body.decision == "No-Show":
        a.interview_score = None
        a.status = Status.INTERVIEW_COMPLETED
        fuse(a)
    audit(db, me, "INTERVIEWER_STATUS", "application", a.id, f"{a.candidate.full_name}: {body.decision}")
    db.commit()
    return {"interviewer_decision": a.interviewer_decision, "status": a.status}


@router.post("/interviews/{app_id}/notes")
def add_note(app_id: int, body: TextIn, db: Session = Depends(get_db), me: User = Depends(require_interviewer)):
    a = _mine(db, app_id, me)
    db.add(Note(application_id=a.id, author_id=me.id, text=body.text))
    audit(db, me, "NOTE_ADDED", "application", a.id, body.text[:120])
    db.commit()
    db.refresh(a)
    return app_detail(a, for_interviewer=True)["notes"]
