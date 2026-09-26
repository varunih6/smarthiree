"""Pydantic request bodies (validation happens here)."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

RoleName = Literal["admin", "interviewer", "candidate"]


def _strong(pw: str) -> str:
    if len(pw) < 6:
        raise ValueError("Password must be at least 6 characters")
    return pw


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    role: RoleName


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    mobile: str
    password: str
    confirm_password: str

    @field_validator("full_name")
    @classmethod
    def name_ok(cls, v):
        return v.strip()

    @field_validator("mobile")
    @classmethod
    def mobile_ok(cls, v):
        v = re.sub(r"[\s-]", "", v)
        if not re.fullmatch(r"\+?\d{10,13}", v):
            raise ValueError("Enter a valid mobile number (10-13 digits)")
        return v

    @field_validator("password")
    @classmethod
    def pw_ok(cls, v):
        return _strong(v)

    @model_validator(mode="after")
    def match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ResetPasswordIn(BaseModel):
    email: EmailStr
    new_password: str
    confirm_password: str
    role: RoleName | None = None

    @field_validator("new_password")
    @classmethod
    def pw_ok(cls, v):
        return _strong(v)

    @model_validator(mode="after")
    def match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class InterviewerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str
    mobile: str | None = None
    designation: str | None = None

    @field_validator("password")
    @classmethod
    def pw_ok(cls, v):
        return _strong(v)


class InterviewerUpdate(BaseModel):
    full_name: str | None = None
    mobile: str | None = None
    designation: str | None = None
    is_active: bool | None = None
    password: str | None = None


class JDIn(BaseModel):
    title: str = Field(min_length=2)
    department: str = "Engineering"
    location: str = "Bengaluru"
    experience: str = "0-2 years"
    description: str = ""
    must_have_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    ats_threshold: float = Field(60, ge=0, le=100)
    weight_resume: float = Field(0.4, ge=0, le=1)
    weight_assessment: float = Field(0.3, ge=0, le=1)
    weight_interview: float = Field(0.3, ge=0, le=1)
    pass_threshold: float = Field(70, ge=0, le=100)
    hold_threshold: float = Field(50, ge=0, le=100)
    confidence_cutoff: float = Field(0.6, ge=0, le=1)
    num_questions: int = Field(5, ge=1, le=20)
    is_active: bool = True

    @model_validator(mode="after")
    def weights(self):
        if self.weight_resume + self.weight_assessment + self.weight_interview <= 0:
            raise ValueError("At least one weight must be > 0")
        if self.hold_threshold > self.pass_threshold:
            raise ValueError("Hold threshold must be <= pass threshold")
        return self


class QuestionIn(BaseModel):
    text: str = Field(min_length=5)
    rubric: list[str] = []
    difficulty: str = "medium"
    time_limit_sec: int = Field(120, ge=15, le=1800)


class ScheduleIn(BaseModel):
    interviewer_id: int
    slot_id: int | None = None
    start: datetime | None = None  # custom time if no slot chosen


class DecisionIn(BaseModel):
    decision: Literal["OFFER", "REJECT", "HOLD"]
    note: str | None = None


class ReviewIn(BaseModel):
    # APPROVE -> interview, PROMOTE -> manual override of ATS filter
    action: Literal["APPROVE", "REJECT", "HOLD", "PROMOTE"]
    note: str | None = None


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class SlotsIn(BaseModel):
    starts: list[datetime]
    duration_min: int = Field(60, ge=15, le=240)


class EvaluationIn(BaseModel):
    technical: int = Field(ge=1, le=5)
    problem_solving: int = Field(ge=1, le=5)
    projects: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)
    overall: int = Field(ge=1, le=5)
    comments: str = ""
    decision: Literal["Accepted", "Rejected", "On-Hold", "No-Show"]


class StatusIn(BaseModel):
    decision: Literal["Accepted", "Rejected", "On-Hold", "No-Show"]


class ResumeTextIn(BaseModel):
    text: str = Field(min_length=30)
    filename: str | None = None


class AnswerIn(BaseModel):
    answer_id: int
    answer: str = ""
    time_taken_sec: int | None = None
    timed_out: bool = False


class TelemetryIn(BaseModel):
    event: Literal["tab_switch", "paste", "copy", "fullscreen_exit", "blur", "context_menu"]
    detail: str | None = None


class OfferResponseIn(BaseModel):
    response: Literal["ACCEPTED", "DECLINED"]
