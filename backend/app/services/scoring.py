"""
AI scoring pipeline:
  resume_match  -> Application.resume_score (+ matched skills, gaps, summary)
  answer_score  -> AssessmentAnswer.score / confidence / rubric hits
  fuse()        -> combined score + PASS / HOLD / REJECT band + auto flags
"""
import logging
import threading

from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..llm import heuristics, llm_client
from ..llm.prompts import (ANSWER_SCORE_SCHEMA, RESUME_MATCH_SCHEMA,
                           answer_score_prompt, resume_match_prompt)
from ..models import (Application, AssessmentAnswer, JobDescription, Status, now)
from .audit import audit, notify

log = logging.getLogger("smarthire.scoring")

PRE_ASSESSMENT = (Status.APPLIED, Status.SCREENING, Status.FILTERED)


# ------------------------------------------------------------------ primitives
def run_resume_match(jd: JobDescription, resume_text: str) -> tuple[dict, str]:
    if llm_client.is_enabled():
        try:
            return llm_client.call(resume_match_prompt(jd, resume_text), RESUME_MATCH_SCHEMA), "llm"
        except llm_client.LLMError as e:
            log.error("resume_match failed cleanly: %s", e)
            if not config.LLM_FALLBACK_TO_HEURISTIC:
                raise
    return heuristics.resume_match(jd, resume_text), "heuristic"


def run_answer_score(question, answer_text: str) -> tuple[dict, str]:
    if not (answer_text or "").strip():
        return heuristics.answer_score(question, ""), "rule"
    if llm_client.is_enabled():
        try:
            return llm_client.call(answer_score_prompt(question, answer_text), ANSWER_SCORE_SCHEMA), "llm"
        except llm_client.LLMError as e:
            log.error("answer_score failed cleanly: %s", e)
            if not config.LLM_FALLBACK_TO_HEURISTIC:
                raise
    return heuristics.answer_score(question, answer_text), "heuristic"


# ------------------------------------------------------------------ resume screening
def score_application_resume(db: Session, app: Application, actor=None) -> Application:
    """Score resume vs JD and apply the ATS threshold (auto-promote / archive)."""
    jd = app.jd
    result, source = run_resume_match(jd, app.resume_snapshot or "")
    app.resume_score = round(float(result["score"]), 1)
    app.matched_skills = result["matched_skills"]
    app.gaps = result["gaps"]
    app.resume_summary = result["summary"]
    app.resume_source = source

    if app.resume_score >= jd.ats_threshold:
        app.status = Status.SCREENING
        app.archive_reason = None
    else:
        app.status = Status.FILTERED
        missing = ", ".join(app.gaps[:4]) if app.gaps else "overall fit"
        app.archive_reason = (f"Resume score {app.resume_score:g} below ATS threshold "
                              f"{jd.ats_threshold:g}. Gaps: {missing}.")
    fuse(app)
    audit(db, actor, "RESUME_SCORED", "application", app.id,
          f"{app.candidate.full_name} -> {jd.title}: {app.resume_score:g} ({source}) => {app.status}")
    return app


def _batch_worker(jd_id: int, app_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        jd = db.get(JobDescription, jd_id)
        apps = [a for a in (db.get(Application, i) for i in app_ids)
                if a and a.status in PRE_ASSESSMENT and a.assessment_started_at is None]
        jd.batch_status, jd.batch_total, jd.batch_done = "running", len(apps), 0
        db.commit()
        for app in apps:
            try:
                score_application_resume(db, app)
            except Exception as e:  # keep the batch going
                log.exception("batch scoring failed for app %s: %s", app.id, e)
            jd.batch_done += 1
            db.commit()
        jd.batch_status, jd.batch_finished_at = "done", now()
        audit(db, None, "BATCH_SCORED", "jd", jd.id, f"{jd.title}: {len(apps)} resumes scored")
        db.commit()
    except Exception:
        log.exception("batch job crashed")
        db.rollback()
        jd = db.get(JobDescription, jd_id)
        if jd:
            jd.batch_status = "failed"
            db.commit()
    finally:
        db.close()


def start_batch(jd_id: int, app_ids: list[int]) -> None:
    threading.Thread(target=_batch_worker, args=(jd_id, app_ids), daemon=True).start()


# ------------------------------------------------------------------ assessment
def _score_assessment_worker(app_id: int) -> None:
    db = SessionLocal()
    try:
        app = db.get(Application, app_id)
        for ans in app.answers:
            if ans.score is not None:
                continue
            result, source = run_answer_score(ans.question, ans.answer_text)
            ans.score = round(float(result["score"]), 2)
            ans.justification = result["justification"]
            ans.confidence = round(float(result["confidence"]), 2)
            ans.rubric_hits = result["rubric_hits"]
            ans.source = source
            db.commit()
        scored = [a for a in app.answers if a.score is not None]
        if scored:
            app.assessment_score = round(sum(a.score for a in scored) / len(scored), 2)
            app.assessment_pct = round(app.assessment_score / 5 * 100, 1)
            confs = [a.confidence for a in scored if a.confidence is not None]
            app.avg_confidence = round(sum(confs) / len(confs), 2) if confs else None
        app.assessment_scoring = "done"
        fuse(app)
        audit(db, None, "ASSESSMENT_SCORED", "application", app.id,
              f"{app.candidate.full_name}: {app.assessment_score}/5, band {app.band}")
        db.commit()
    except Exception:
        log.exception("assessment scoring failed for %s", app_id)
        db.rollback()
    finally:
        db.close()


def start_assessment_scoring(app_id: int) -> None:
    threading.Thread(target=_score_assessment_worker, args=(app_id,), daemon=True).start()


# ------------------------------------------------------------------ fusion + flags
def fuse(app: Application) -> None:
    jd = app.jd
    parts = []
    if app.resume_score is not None:
        parts.append((jd.weight_resume, app.resume_score))
    if app.assessment_pct is not None:
        parts.append((jd.weight_assessment, app.assessment_pct))
    if app.interview_score is not None:
        parts.append((jd.weight_interview, app.interview_score))
    total_w = sum(w for w, _ in parts)
    if parts and total_w > 0:
        app.combined_score = round(sum(w * s for w, s in parts) / total_w, 1)
        if app.combined_score >= jd.pass_threshold:
            app.band = "PASS"
        elif app.combined_score >= jd.hold_threshold:
            app.band = "HOLD"
        else:
            app.band = "REJECT"
    app.flags = compute_flags(app)


def compute_flags(app: Application) -> list[dict]:
    jd = app.jd
    flags = []
    if app.avg_confidence is not None and app.avg_confidence < jd.confidence_cutoff:
        flags.append({"code": "LOW_CONFIDENCE", "severity": "warn",
                      "label": f"Avg AI confidence {app.avg_confidence:.2f} < {jd.confidence_cutoff:g}"})
    if app.resume_score is not None and app.assessment_pct is not None:
        diff = abs(app.resume_score - app.assessment_pct)
        if diff >= 35:
            flags.append({"code": "SCORE_DISAGREEMENT", "severity": "warn",
                          "label": f"Resume ({app.resume_score:g}) vs Q&A ({app.assessment_pct:g}) differ by {diff:.0f}"})
    if app.tab_switches:
        flags.append({"code": "TAB_SWITCH", "severity": "danger" if app.tab_switches >= 3 else "warn",
                      "label": f"{app.tab_switches} tab switch(es)"})
    if app.paste_events:
        flags.append({"code": "PASTE", "severity": "danger", "label": f"{app.paste_events} paste attempt(s)"})
    if app.copy_events:
        flags.append({"code": "COPY", "severity": "warn", "label": f"{app.copy_events} copy attempt(s)"})
    if app.fullscreen_exits:
        flags.append({"code": "FULLSCREEN_EXIT", "severity": "warn",
                      "label": f"Exited full screen {app.fullscreen_exits} time(s)"})
    timeouts = sum(1 for a in app.answers if a.timed_out)
    if timeouts >= 2:
        flags.append({"code": "TIMEOUTS", "severity": "info", "label": f"{timeouts} question(s) timed out"})
    if app.resume_source == "heuristic" and llm_client.is_enabled():
        flags.append({"code": "LLM_FALLBACK", "severity": "info", "label": "LLM failed; heuristic score used"})
    return flags


def system_recommendation(app: Application) -> str | None:
    if app.band is None:
        return None
    danger = any(f["severity"] == "danger" for f in (app.flags or []))
    if app.band == "PASS" and not danger:
        return "ADVANCE"
    if app.band == "REJECT":
        return "REJECT"
    return "REVIEW"


def notify_candidate(app: Application, subject: str) -> None:
    notify(app.candidate.email, subject, f"Application #{app.id} - {app.jd.title}")
