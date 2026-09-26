"""
Central configuration. Values come from backend/.env (see .env.example).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- database
# Hackathon spec: in-memory SQLite. Data survives page refreshes but NOT a
# server restart. Switch to "sqlite:///./smarthire.db" if you want it on disk.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///:memory:")
SEED_FILE = Path(os.getenv("SEED_FILE", str(BASE_DIR / "data" / "Input_Data.json")))

# ---------------------------------------------------------------- auth / JWT
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-smarthire-dev-secret-please-rotate")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

# ---------------------------------------------------------------- master admin
# The ONE admin account is hard-coded here (override via .env). It is written
# into the database (bcrypt-hashed) at startup; login still checks the DB.
MASTER_ADMIN_NAME = os.getenv("MASTER_ADMIN_NAME", "Master Admin")
MASTER_ADMIN_EMAIL = os.getenv("MASTER_ADMIN_EMAIL", "admin@smarthire.com").lower()
MASTER_ADMIN_PASSWORD = os.getenv("MASTER_ADMIN_PASSWORD", "Admin@123")
# If the seed JSON contains admin users, ignore them (exactly one admin rule).
SEED_JSON_ADMINS = _bool("SEED_JSON_ADMINS", False)

# ---------------------------------------------------------------- LLM
# LLM_PROVIDER: "openai" | "anthropic" | "openai_compatible" | "mock"
#   mock  -> no API key needed, deterministic keyword-based scoring (demo mode)
#   openai_compatible -> Groq / Gemini (OpenAI endpoint) / Ollama / OpenRouter …
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "40"))
# If the real LLM fails twice, fall back to heuristic scoring (marked in UI).
LLM_FALLBACK_TO_HEURISTIC = _bool("LLM_FALLBACK_TO_HEURISTIC", True)

# ---------------------------------------------------------------- misc
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
MAX_RESUME_CHARS = 20000
