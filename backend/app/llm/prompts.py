"""
Exactly TWO single-turn structured prompts.
These are never sent to the candidate UI.
"""
import json

RESUME_MATCH_SCHEMA = {
    "score": {"type": "number", "min": 0, "max": 100},
    "matched_skills": {"type": "array"},
    "gaps": {"type": "array"},
    "summary": {"type": "string"},
}

ANSWER_SCORE_SCHEMA = {
    "score": {"type": "number", "min": 0, "max": 5},
    "justification": {"type": "string"},
    "confidence": {"type": "number", "min": 0, "max": 1},
    "rubric_hits": {"type": "array"},
}


def resume_match_prompt(jd, resume_text: str) -> str:
    return f"""TASK: resume_match
Evaluate how well the RESUME matches the JOB DESCRIPTION.

JOB DESCRIPTION
Title: {jd.title}
Experience required: {jd.experience}
Must-have skills: {", ".join(jd.must_have_skills)}
Nice-to-have skills: {", ".join(jd.nice_to_have_skills)}
Description: {jd.description}

RESUME (plain text)
\"\"\"
{resume_text[:8000]}
\"\"\"

Scoring guide: must-have skills carry ~70% of the score, relevant experience ~20%,
nice-to-have skills ~10%. Only credit skills with evidence in the resume.

Return ONLY this JSON:
{{"score": <integer 0-100>,
  "matched_skills": [<skills from the JD found in the resume>],
  "gaps": [<must-have skills missing or weak>],
  "summary": "<2-3 sentence evidence-based justification>"}}"""


def answer_score_prompt(question, answer_text: str) -> str:
    rubric = [r.get("point", r) if isinstance(r, dict) else r for r in (question.rubric or [])]
    return f"""TASK: answer_score
Grade the CANDIDATE ANSWER to the technical QUESTION using the RUBRIC.

QUESTION: {question.text}
RUBRIC POINTS: {json.dumps(rubric)}

CANDIDATE ANSWER:
\"\"\"
{(answer_text or '').strip()[:4000] or '(no answer)'}
\"\"\"

Scoring guide: 0 = blank/irrelevant, 1-2 = partial, 3 = adequate, 4 = strong, 5 = excellent
and covers every rubric point. confidence = how sure you are of the grade (0-1).
rubric_hits = the rubric points the answer clearly covers (copy the text).

Return ONLY this JSON:
{{"score": <number 0-5>, "justification": "<1-2 sentences>",
  "confidence": <number 0-1>, "rubric_hits": [<rubric points covered>]}}"""
