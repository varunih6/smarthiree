"""Meeting creation service for interviews."""

from uuid import uuid4


JITSI_BASE_URL = "https://meet.jit.si"


def create_interview_meeting(application_id: int) -> str:
    """
    Create a unique Jitsi meeting URL for an application.

    The meeting is created lazily by generating a unique room name.
    Jitsi creates the actual room when the first participant joins.
    """
    room_id = f"smarthire-interview-{application_id}-{uuid4().hex[:12]}"

    return f"{JITSI_BASE_URL}/{room_id}"