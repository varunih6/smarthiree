import logging

from sqlalchemy.orm import Session

from ..models import AuditLog, User

log = logging.getLogger("smarthire")


def audit(db: Session, actor: User | None, action: str, entity: str = "",
          entity_id: int | None = None, details: str = "") -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else "system",
        actor_role=actor.role if actor else "system",
        action=action, entity=entity, entity_id=entity_id, details=details,
    ))


def notify(to_email: str, subject: str, body: str = "") -> None:
    """Stub: no real email/SMS. Logged to the console; the UI shows toasts."""
    log.info("[NOTIFY] to=%s | %s | %s", to_email, subject, body)
    print(f"[NOTIFY] -> {to_email}: {subject} {('- ' + body) if body else ''}", flush=True)
