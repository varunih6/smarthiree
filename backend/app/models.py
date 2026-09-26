"""
SQLAlchemy ORM models — single source of truth for the whole pipeline.
"""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


class Role:
    ADMIN = "admin"
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"
    ALL = (ADMIN, INTERVIEWER, CANDIDATE)


class Status:
    """Application pipeline states (internal)."""
    APPLIED = "APPLIED"                          # waiting for resume scoring
    FILTERED = "FILTERED"                        # below ATS threshold (archived)
    SCREENING = "SCREENING"                      # passed ATS -> assessment unlocked
    ASSESSMENT_IN_PROGRESS = "ASSESSMENT_IN_PROGRESS"
    ASSESSMENT_SUBMITTED = "ASSESSMENT_SUBMITTED"  # waiting for admin review
    INTERVIEW_PENDING = "INTERVIEW_PENDING"      # admin approved, needs slot
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"  # evaluation submitted
    ON_HOLD = "ON_HOLD"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_DECLINED = "OFFER_DECLINED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # UNIQUE in DB; SQLite allows many NULLs, so interviewers may leave it empty.
    mobile: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_master: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # candidate-only profile fields
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resume_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # interviewer-only
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    department: Mapped[str] = mapped_column(String(100), default="Engineering")
    location: Mapped[str] = mapped_column(String(100), default="Bengaluru")
    experience: Mapped[str] = mapped_column(String(50), default="0-2 years")
    description: Mapped[str] = mapped_column(Text, default="")
    must_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_to_have_skills: Mapped[list] = mapped_column(JSON, default=list)

    # screening configuration (editable by admin)
    ats_threshold: Mapped[float] = mapped_column(Float, default=60)        # resume score cut-off
    weight_resume: Mapped[float] = mapped_column(Float, default=0.4)
    weight_assessment: Mapped[float] = mapped_column(Float, default=0.3)
    weight_interview: Mapped[float] = mapped_column(Float, default=0.3)
    pass_threshold: Mapped[float] = mapped_column(Float, default=70)       # combined >= -> PASS
    hold_threshold: Mapped[float] = mapped_column(Float, default=50)       # combined >= -> HOLD
    confidence_cutoff: Mapped[float] = mapped_column(Float, default=0.6)
    num_questions: Mapped[int] = mapped_column(Integer, default=5)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    # batch LLM job state
    batch_status: Mapped[str] = mapped_column(String(20), default="idle")  # idle|running|done|failed
    batch_total: Mapped[int] = mapped_column(Integer, default=0)
    batch_done: Mapped[int] = mapped_column(Integer, default=0)
    batch_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    questions = relationship("Question", back_populates="jd", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"))
    text: Mapped[str] = mapped_column(Text)
    # list of {"point": str, "keywords": [str]}
    rubric: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=120)

    jd = relationship("JobDescription", back_populates="questions")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "jd_id", name="uq_candidate_jd"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"))
    status: Mapped[str] = mapped_column(String(40), default=Status.APPLIED, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    # --- resume screening (hidden from candidate)
    resume_snapshot: Mapped[str] = mapped_column(Text, default="")
    resume_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    resume_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # llm|heuristic
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- online assessment
    assessment_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assessment_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assessment_scoring: Mapped[str] = mapped_column(String(20), default="none")  # none|pending|done
    assessment_score: Mapped[float | None] = mapped_column(Float, nullable=True)   # avg 0-5
    assessment_pct: Mapped[float | None] = mapped_column(Float, nullable=True)     # 0-100
    avg_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tab_switches: Mapped[int] = mapped_column(Integer, default=0)
    paste_events: Mapped[int] = mapped_column(Integer, default=0)
    copy_events: Mapped[int] = mapped_column(Integer, default=0)
    fullscreen_exits: Mapped[int] = mapped_column(Integer, default=0)
    telemetry_log: Mapped[list] = mapped_column(JSON, default=list)

    # --- fusion
    combined_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    band: Mapped[str | None] = mapped_column(String(10), nullable=True)  # PASS|HOLD|REJECT
    flags: Mapped[list] = mapped_column(JSON, default=list)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- interview
    interviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interview_slot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_by: Mapped[str | None] = mapped_column(String(20), nullable=True)  # auto|manual
    interview_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    interviewer_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- final
    final_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)  # OFFER|REJECT|HOLD
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    candidate_response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    candidate = relationship("User", foreign_keys=[candidate_id])
    interviewer = relationship("User", foreign_keys=[interviewer_id])
    jd = relationship("JobDescription")
    answers = relationship("AssessmentAnswer", back_populates="application",
                           cascade="all, delete-orphan", order_by="AssessmentAnswer.order")
    evaluations = relationship("Evaluation", back_populates="application",
                               cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="application", cascade="all, delete-orphan",
                         order_by="Note.created_at")


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    served_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    time_taken_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)           # 0-5
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)      # 0-1
    rubric_hits: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    application = relationship("Application", back_populates="answers")
    question = relationship("Question")


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (UniqueConstraint("interviewer_id", "start", name="uq_interviewer_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    application_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    technical: Mapped[int] = mapped_column(Integer)
    problem_solving: Mapped[int] = mapped_column(Integer)
    projects: Mapped[int] = mapped_column(Integer)
    communication: Mapped[int] = mapped_column(Integer)
    overall: Mapped[int] = mapped_column(Integer)
    comments: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(String(20))  # Accepted|Rejected|On-Hold|No-Show
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    application = relationship("Application", back_populates="evaluations")
    interviewer = relationship("User")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    application = relationship("Application", back_populates="notes")
    author = relationship("User")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="system")
    actor_role: Mapped[str] = mapped_column(String(20), default="system")
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
