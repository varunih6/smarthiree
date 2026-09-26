"""
Smart interview scheduler.
Matches candidates waiting for an interview (INTERVIEW_PENDING) with free
interviewer availability slots:
  * highest combined score gets scheduled first
  * earliest free slot wins; ties go to the interviewer with the lighter load
  * never double-books an interviewer or a candidate at the same time
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Application, AvailabilitySlot, Role, Status, User
from .audit import audit
from .scoring import notify_candidate


def _load(db: Session, interviewer_id: int) -> int:
    return db.query(Application).filter(
        Application.interviewer_id == interviewer_id,
        Application.status == Status.INTERVIEW_SCHEDULED).count()


def book(db: Session, app: Application, slot: AvailabilitySlot, actor: User | None, mode: str):
    # free a previous slot if re-scheduling
    if app.interview_slot_id:
        old = db.get(AvailabilitySlot, app.interview_slot_id)
        if old and old.id != slot.id:
            old.is_booked, old.application_id = False, None
    slot.is_booked, slot.application_id = True, app.id
    app.interviewer_id = slot.interviewer_id
    app.interview_at = slot.start
    app.interview_slot_id = slot.id
    app.scheduled_by = mode
    app.status = Status.INTERVIEW_SCHEDULED
    interviewer = db.get(User, slot.interviewer_id)
    audit(db, actor, "INTERVIEW_SCHEDULED", "application", app.id,
          f"{app.candidate.full_name} with {interviewer.full_name} at "
          f"{slot.start:%d %b %Y %H:%M} ({mode})")
    notify_candidate(app, f"Interview scheduled on {slot.start:%d %b %Y, %I:%M %p}")


def auto_schedule(db: Session, actor: User, jd_id: int | None = None) -> dict:
    q = db.query(Application).filter(Application.status == Status.INTERVIEW_PENDING)
    if jd_id:
        q = q.filter(Application.jd_id == jd_id)
    pending = sorted(q.all(), key=lambda a: -(a.combined_score or 0))

    active_ids = {u.id for u in db.query(User).filter(
        User.role == Role.INTERVIEWER, User.is_active.is_(True))}
    earliest = datetime.now() + timedelta(minutes=30)

    scheduled, unscheduled = [], []
    for app in pending:
        # times the candidate is already busy (other applications)
        busy = {a.interview_at for a in db.query(Application).filter(
            Application.candidate_id == app.candidate_id,
            Application.status == Status.INTERVIEW_SCHEDULED) if a.interview_at}
        free = [s for s in db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.is_booked.is_(False),
                    AvailabilitySlot.start >= earliest).order_by(AvailabilitySlot.start)
                if s.interviewer_id in active_ids and s.start not in busy]
        if not free:
            unscheduled.append({"application_id": app.id, "candidate": app.candidate.full_name,
                                "reason": "No free interviewer slots"})
            continue
        first_time = free[0].start
        same_time = [s for s in free if s.start == first_time]
        slot = min(same_time, key=lambda s: _load(db, s.interviewer_id))
        book(db, app, slot, actor, "auto")
        db.flush()
        scheduled.append({"application_id": app.id, "candidate": app.candidate.full_name,
                          "interviewer": db.get(User, slot.interviewer_id).full_name,
                          "at": slot.start.isoformat()})
    audit(db, actor, "AUTO_SCHEDULE_RUN", "schedule", None,
          f"{len(scheduled)} scheduled, {len(unscheduled)} could not be scheduled")
    return {"scheduled": scheduled, "unscheduled": unscheduled}
