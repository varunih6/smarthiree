"""
Serializers. Admin/interviewer views include AI evidence; the candidate view
deliberately exposes NO scores, justifications, flags or prompts.
"""
import re

from ..models import Application, JobDescription, Status, User
from .scoring import system_recommendation

CANDIDATE_STATUS = {
    Status.APPLIED: ("Applied", "Your application has been received and is being reviewed."),
    Status.FILTERED: ("Not Shortlisted", "Thank you for applying. Unfortunately your profile was not shortlisted for this role."),
    Status.SCREENING: ("Shortlisted for Assessment", "You cleared the initial screening! Take the online assessment."),
    Status.ASSESSMENT_IN_PROGRESS: ("Assessment In Progress", "You have started the online assessment."),
    Status.ASSESSMENT_SUBMITTED: ("Assessment Completed", "Your assessment has been submitted. Please wait for an update."),
    Status.INTERVIEW_PENDING: ("Shortlisted for Interview", "Great work! Your interview will be scheduled shortly."),
    Status.INTERVIEW_SCHEDULED: ("Interview Scheduled", "Your interview has been scheduled. Details below."),
    Status.INTERVIEW_COMPLETED: ("Interview Completed", "Your interview is complete. The final decision is pending."),
    Status.ON_HOLD: ("On Hold", "Your application is on hold. We will get back to you."),
    Status.OFFERED: ("Offer Released", "Congratulations! You have been selected. Please accept or decline the offer."),
    Status.REJECTED: ("Rejected", "Thank you for your time. We will not be moving forward at this time."),
    Status.OFFER_ACCEPTED: ("Offer Accepted", "You accepted the offer. Welcome aboard!"),
    Status.OFFER_DECLINED: ("Offer Declined", "You declined the offer."),
}


def iso(dt):
    return dt.isoformat() if dt else None


def user_view(u: User) -> dict:
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "mobile": u.mobile,
            "role": u.role, "is_active": u.is_active, "is_master": u.is_master,
            "designation": u.designation, "created_at": iso(u.created_at),
            "has_resume": bool(u.resume_text)}


def jd_view(jd: JobDescription, admin: bool = False) -> dict:
    d = {"id": jd.id, "title": jd.title, "department": jd.department, "location": jd.location,
         "experience": jd.experience, "description": jd.description,
         "must_have_skills": jd.must_have_skills, "nice_to_have_skills": jd.nice_to_have_skills,
         "is_active": jd.is_active, "created_at": iso(jd.created_at)}
    if admin:
        d.update({k: getattr(jd, k) for k in (
            "ats_threshold", "weight_resume", "weight_assessment", "weight_interview",
            "pass_threshold", "hold_threshold", "confidence_cutoff", "num_questions",
            "batch_status", "batch_total", "batch_done")})
        d["batch_finished_at"] = iso(jd.batch_finished_at)
        d["question_count"] = len(jd.questions)
    return d


def question_view(q, with_rubric=True) -> dict:
    d = {"id": q.id, "jd_id": q.jd_id, "text": q.text, "difficulty": q.difficulty,
         "time_limit_sec": q.time_limit_sec}
    if with_rubric:
        d["rubric"] = [r.get("point", r) if isinstance(r, dict) else r for r in q.rubric or []]
    return d


def evaluation_view(e) -> dict:
    return {"id": e.id, "interviewer": e.interviewer.full_name, "interviewer_id": e.interviewer_id,
            "technical": e.technical, "problem_solving": e.problem_solving,
            "projects": e.projects, "communication": e.communication, "overall": e.overall,
            "average": round((e.technical + e.problem_solving + e.projects + e.communication + e.overall) / 5, 2),
            "comments": e.comments, "decision": e.decision, "created_at": iso(e.created_at)}


def app_summary(a: Application) -> dict:
    """Row for admin pipeline tables (AI signals included)."""
    return {
        "id": a.id, "status": a.status,
        "candidate_id": a.candidate_id, "candidate_name": a.candidate.full_name,
        "candidate_email": a.candidate.email, "jd_id": a.jd_id, "jd_title": a.jd.title,
        "resume_score": a.resume_score, "assessment_score": a.assessment_score,
        "assessment_pct": a.assessment_pct, "interview_score": a.interview_score,
        "combined_score": a.combined_score, "band": a.band, "flags": a.flags or [],
        "avg_confidence": a.avg_confidence, "assessment_scoring": a.assessment_scoring,
        "recommendation": system_recommendation(a) if a.assessment_scoring == "done" else None,
        "interviewer_id": a.interviewer_id,
        "interviewer_name": a.interviewer.full_name if a.interviewer else None,
        "interview_at": iso(a.interview_at), "scheduled_by": a.scheduled_by,
        "interviewer_decision": a.interviewer_decision, "final_decision": a.final_decision,
        "candidate_response": a.candidate_response, "archive_reason": a.archive_reason,
        "created_at": iso(a.created_at), "updated_at": iso(a.updated_at),
    }


def app_detail(a: Application, for_interviewer: bool = False) -> dict:
    d = app_summary(a)
    d.update({
        "candidate": user_view(a.candidate),
        "jd": jd_view(a.jd, admin=not for_interviewer),
        "resume_text": a.resume_snapshot,
        "matched_skills": a.matched_skills or [], "gaps": a.gaps or [],
        "resume_summary": a.resume_summary, "resume_source": a.resume_source,
        "assessment_started_at": iso(a.assessment_started_at),
        "assessment_submitted_at": iso(a.assessment_submitted_at),
        "answers": [{
            "order": x.order + 1, "question": x.question.text,
            "rubric": question_view(x.question)["rubric"],
            "answer": x.answer_text, "time_taken_sec": x.time_taken_sec,
            "time_limit_sec": x.question.time_limit_sec, "timed_out": x.timed_out,
            "score": x.score, "justification": x.justification, "confidence": x.confidence,
            "rubric_hits": x.rubric_hits or [], "source": x.source,
            "submitted": x.submitted_at is not None,
        } for x in a.answers],
        "evaluations": [evaluation_view(e) for e in a.evaluations],
        "notes": [{"id": n.id, "author": n.author.full_name, "role": n.author.role,
                   "text": n.text, "created_at": iso(n.created_at)} for n in a.notes],
        "next_steps": a.next_steps,
        "decided_at": iso(a.decided_at), "responded_at": iso(a.responded_at),
    })
    if not for_interviewer:
        d["telemetry"] = {"tab_switches": a.tab_switches, "paste_events": a.paste_events,
                          "copy_events": a.copy_events, "fullscreen_exits": a.fullscreen_exits,
                          "log": (a.telemetry_log or [])[-50:]}
    return d


def candidate_app_view(a: Application) -> dict:
    """What the candidate sees: status + dates. No AI scores or reasons."""
    label, message = CANDIDATE_STATUS.get(a.status, (a.status, ""))
    timeline = [{"label": "Applied", "date": iso(a.created_at), "done": True}]
    if a.status == Status.FILTERED:
        timeline.append({"label": "Not shortlisted", "date": iso(a.updated_at), "done": True, "bad": True})
    elif a.status != Status.APPLIED:
        timeline.append({"label": "Shortlisted for Assessment", "date": None, "done": True})
        timeline.append({"label": "Assessment Completed", "date": iso(a.assessment_submitted_at),
                         "done": a.assessment_submitted_at is not None})
        reached_interview = a.status in (Status.INTERVIEW_PENDING, Status.INTERVIEW_SCHEDULED,
                                         Status.INTERVIEW_COMPLETED, Status.OFFERED,
                                         Status.OFFER_ACCEPTED, Status.OFFER_DECLINED) or a.interview_at
        timeline.append({"label": "Shortlisted for Interview", "date": None, "done": bool(reached_interview)})
        timeline.append({"label": "Interview Scheduled", "date": iso(a.interview_at),
                         "done": a.interview_at is not None})
        if a.final_decision:
            timeline.append({"label": {"OFFER": "Offer Released", "REJECT": "Rejected",
                                       "HOLD": "On Hold"}[a.final_decision],
                             "date": iso(a.decided_at), "done": True, "bad": a.final_decision == "REJECT"})
        elif a.status == Status.REJECTED:
            timeline.append({"label": "Rejected", "date": iso(a.updated_at), "done": True, "bad": True})
        else:
            timeline.append({"label": "Final Decision", "date": None, "done": False})
        if a.candidate_response:
            timeline.append({"label": f"Offer {a.candidate_response.title()}", "date": iso(a.responded_at),
                             "done": True, "bad": a.candidate_response == "DECLINED"})
    return {
        "id": a.id, "jd_id": a.jd_id, "jd_title": a.jd.title, "location": a.jd.location,
        "status": a.status, "status_label": label, "status_message": message,
        "applied_at": iso(a.created_at), "updated_at": iso(a.updated_at),
        "can_take_assessment": a.status in (Status.SCREENING, Status.ASSESSMENT_IN_PROGRESS),
        "interview": ({"at": iso(a.interview_at),
                       "interviewer": a.interviewer.full_name if a.interviewer else None,
                       "mode": "Online (video call link will be shared)"}
                      if a.interview_at and a.status == Status.INTERVIEW_SCHEDULED else None),
        "can_respond_offer": a.status == Status.OFFERED,
        "has_offer_letter": a.status in (Status.OFFERED, Status.OFFER_ACCEPTED),
        "timeline": timeline,
    }


def match_priority(jd: JobDescription, resume_text: str | None) -> str | None:
    """Coarse JD priority for the candidate (High/Medium/Low) — not the ATS score."""
    if not resume_text:
        return None
    text = resume_text.lower()
    skills = (jd.must_have_skills or []) + (jd.nice_to_have_skills or [])
    if not skills:
        return "Medium"
    hits = sum(1 for s in skills if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", text))
    ratio = hits / len(skills)
    return "High" if ratio >= 0.5 else "Medium" if ratio >= 0.25 else "Low"
