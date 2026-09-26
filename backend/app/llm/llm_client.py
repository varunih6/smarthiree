"""
Single swappable LLM wrapper:  llm_client.call(prompt, schema) -> dict

* Provider picked from .env (LLM_PROVIDER = openai | anthropic | openai_compatible | mock)
* Single-turn, non-agentic. Returns strict JSON validated against `schema`.
* Guardrail: at most ONE retry (invalid JSON / schema mismatch / 4xx / 5xx / timeout),
  then raises LLMError so the caller can fail cleanly.

Schema format (tiny, dependency-free):
    {"score": {"type": "number", "min": 0, "max": 100},
     "matched_skills": {"type": "array"},
     "summary": {"type": "string"}}
"""
import json
import logging
import re

import httpx

from .. import config

log = logging.getLogger("smarthire.llm")

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai_compatible": "llama-3.1-8b-instant",
}

SYSTEM_PROMPT = (
    "You are a strict, fair technical recruiting evaluator. "
    "Reply with ONE JSON object only. No markdown, no code fences, no commentary."
)


class LLMError(Exception):
    pass


def is_enabled() -> bool:
    return config.LLM_PROVIDER != "mock" and bool(config.LLM_API_KEY or config.LLM_PROVIDER == "openai_compatible")


def provider_label() -> str:
    if not is_enabled():
        return "mock (heuristic)"
    return f"{config.LLM_PROVIDER}:{config.LLM_MODEL or DEFAULT_MODELS.get(config.LLM_PROVIDER, '')}"


# ------------------------------------------------------------------ transport
def _post_openai(prompt: str, base_url: str) -> str:
    model = config.LLM_MODEL or DEFAULT_MODELS["openai"]
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    r = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=body,
                   headers=headers, timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _post_anthropic(prompt: str) -> str:
    model = config.LLM_MODEL or DEFAULT_MODELS["anthropic"]
    base = config.LLM_BASE_URL or "https://api.anthropic.com"
    r = httpx.post(
        f"{base.rstrip('/')}/v1/messages",
        headers={"x-api-key": config.LLM_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 1024, "temperature": 0, "system": SYSTEM_PROMPT,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=config.LLM_TIMEOUT,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []))


def _raw_call(prompt: str) -> str:
    p = config.LLM_PROVIDER
    if p == "openai":
        return _post_openai(prompt, config.LLM_BASE_URL or "https://api.openai.com/v1")
    if p == "openai_compatible":
        if not config.LLM_BASE_URL:
            raise LLMError("LLM_BASE_URL is required for openai_compatible provider")
        return _post_openai(prompt, config.LLM_BASE_URL)
    if p == "anthropic":
        return _post_anthropic(prompt)
    raise LLMError(f"LLM provider '{p}' is not a real provider (mock mode)")


# ------------------------------------------------------------------ parsing
def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def validate(data, schema: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Response is not a JSON object")
    out = {}
    for key, rule in schema.items():
        if key not in data:
            raise ValueError(f"Missing key '{key}'")
        val = data[key]
        t = rule.get("type")
        if t == "number":
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    raise ValueError(f"'{key}' must be a number")
            lo, hi = rule.get("min"), rule.get("max")
            if lo is not None and hi is not None and not (lo <= val <= hi):
                raise ValueError(f"'{key}'={val} outside [{lo},{hi}]")
        elif t == "array":
            if not isinstance(val, list):
                raise ValueError(f"'{key}' must be an array")
            val = [str(v) for v in val]
        elif t == "string":
            val = "" if val is None else str(val)
        out[key] = val
    return out


# ------------------------------------------------------------------ public
def call(prompt: str, schema: dict) -> dict:
    if not is_enabled():
        raise LLMError("LLM disabled (mock mode)")

    last_err: Exception | None = None
    current_prompt = prompt
    for attempt in (1, 2):  # original + at most ONE retry
        try:
            raw = _raw_call(current_prompt)
            return validate(_extract_json(raw), schema)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            last_err = LLMError(f"HTTP {code}: {e.response.text[:200]}")
            log.warning("LLM attempt %s failed with HTTP %s", attempt, code)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = LLMError(f"Invalid JSON from LLM: {e}")
            log.warning("LLM attempt %s returned invalid JSON: %s", attempt, e)
            current_prompt = (prompt + "\n\nIMPORTANT: your previous reply was not valid JSON "
                              "for the required schema. Return ONLY the JSON object.")
        except (httpx.HTTPError, KeyError, IndexError) as e:
            last_err = LLMError(f"LLM transport error: {e}")
            log.warning("LLM attempt %s transport error: %s", attempt, e)
    raise last_err or LLMError("Unknown LLM failure")
