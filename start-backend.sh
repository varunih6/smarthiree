#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then python3 -m venv .venv; . .venv/bin/activate; pip install -r requirements.txt; else . .venv/bin/activate; fi
[ -f .env ] || cp .env.example .env
uvicorn app.main:app --reload --port 8000
