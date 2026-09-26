"""
Deterministic keyword scorer used when no LLM key is configured (mock mode)
or when the real LLM fails twice. Same output shape as the LLM prompts.
"""
import re

STOP = set("""a an the and or of to in on for with by is are be as at that this it from
into using use how what why when which your you can will does do explain describe
between difference its their them they than then also about""".split())


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _has(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    # word-ish boundary match; allow symbols like c++, node.js, ci/cd
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _years(text: str) -> float:
    nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs|year)", text)]
    return max(nums) if nums else 0.0


def _required_years(exp: str) -> float:
    m = re.search(r"(\d+)", exp or "")
    return float(m.group(1)) if m else 0.0


def resume_match(jd, resume_text: str) -> dict:
    text = _norm(resume_text)
    must = jd.must_have_skills or []
    nice = jd.nice_to_have_skills or []
    matched_must = [s for s in must if _has(text, s)]
    matched_nice = [s for s in nice if _has(text, s)]
    gaps = [s for s in must if s not in matched_must]

    must_ratio = len(matched_must) / len(must) if must else 1
    nice_ratio = len(matched_nice) / len(nice) if nice else 1
    need, have = _required_years(jd.experience), _years(text)
    exp_ratio = 1.0 if need == 0 else min(1.0, have / need) if have else 0.4

    score = round(70 * must_ratio + 20 * exp_ratio + 10 * nice_ratio)
    summary = (f"Matched {len(matched_must)}/{len(must)} must-have skills"
               f"{' and ' + str(len(matched_nice)) + ' nice-to-have' if matched_nice else ''}. "
               f"Detected ~{have:g} years of experience vs {jd.experience} required. "
               + (f"Missing: {', '.join(gaps[:5])}." if gaps else "No major skill gaps found."))
    return {"score": max(0, min(100, score)), "matched_skills": matched_must + matched_nice,
            "gaps": gaps, "summary": summary}


def _keywords(point) -> list[str]:
    if isinstance(point, dict) and point.get("keywords"):
        return [k.lower() for k in point["keywords"]]
    text = point.get("point", "") if isinstance(point, dict) else str(point)
    return [w for w in re.findall(r"[a-z0-9+#.]{3,}", text.lower()) if w not in STOP][:6]


def answer_score(question, answer_text: str) -> dict:
    text = _norm(answer_text)
    words = len(text.split())
    rubric = question.rubric or []
    if words == 0:
        return {"score": 0, "justification": "No answer was submitted.", "confidence": 0.95,
                "rubric_hits": []}

    hits = []
    for point in rubric:
        kws = _keywords(point)
        if not kws:
            continue
        found = sum(1 for k in kws if _has(text, k))
        needed = 1 if len(kws) <= 2 else 2
        if found >= needed:
            hits.append(point.get("point", str(point)) if isinstance(point, dict) else str(point))

    ratio = len(hits) / len(rubric) if rubric else 0.5
    depth = min(1.0, words / 60)  # reward reasonably detailed answers
    score = round(5 * (0.8 * ratio + 0.2 * depth), 1)
    confidence = 0.8 if words >= 25 else 0.55 if words >= 8 else 0.45
    just = (f"Covered {len(hits)} of {len(rubric)} rubric points"
            f"{' with good depth' if depth > 0.8 else ''}."
            + ("" if hits else " Answer lacks the key concepts expected."))
    return {"score": score, "justification": just, "confidence": confidence, "rubric_hits": hits}
