# SmartHire Pipeline — AI-Powered Screening & Interview Tracking Portal

React + Vite frontend · FastAPI backend · SQLite (in-memory) + SQLAlchemy · JWT + bcrypt · swappable LLM wrapper.

**The frontend and backend are already integrated.** The Vite dev server proxies every `/api/*` call to FastAPI on port 8000, so you don't need any CORS or URL setup.

---

## 1. Run it in VS Code (about 2 minutes)

You need **Python 3.10+** and **Node 18+**.

Open the `smarthire` folder in VS Code and open **two terminals** (`Ctrl+Shift+``):

**Terminal 1: backend**
```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Mac / Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2: frontend**
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. API docs (Swagger) are at **http://localhost:8000/docs**.

> Shortcut: double-click `start-backend.bat` and `start-frontend.bat` on Windows, or run `./start-backend.sh` and `./start-frontend.sh` on Mac/Linux.

> **In-memory database:** everything resets whenever the backend restarts. With `--reload`, that includes every time you save a Python file. It persists across page refreshes, which is what the spec requires. To keep data while you develop, set `DATABASE_URL=sqlite:///./smarthire.db` in `backend/.env`.

### Docker (single container)
```bash
docker build -t smarthire .
docker run -p 8000:8000 smarthire      # open http://localhost:8000
```

---

## 2. Demo logins

| Role | Email | Password |
|---|---|---|
| **Admin** (the one master admin, hard-coded in `backend/app/config.py` / `.env`) | admin@smarthire.com | Admin@123 |
| Interviewer | john.interviewer@smarthire.com | Interviewer@123 |
| Interviewer | ananya.interviewer@smarthire.com | Interviewer@123 |
| Candidates (10) | aarav@, riya@, karan@, sanjana@, neha@, rohit@, vikram@, priya@, arjun@, meera@ **example.com** | Candidate@123 |

You can also register a brand-new candidate from the landing page.

---

## 3. End-to-end demo script

1. **Admin → Candidate Pipeline → click a job tab.** Selecting a JD automatically runs the LLM batch job, which scores every resume. Candidates above the ATS threshold are promoted to *Screening*; the rest are archived with a reason.
2. **Candidate (e.g. aarav@example.com) → Dashboard → Start assessment.** Full screen, one question at a time, a per-question timer that auto-submits, and copy/paste/tab-switch blocking with telemetry.
3. **Admin → open the candidate.** You'll see the resume evidence, per-answer AI scores/confidence/rubric hits, per-question timings, anti-cheat telemetry, auto-flags, and a system recommendation (ADVANCE / REVIEW / REJECT). Click **Approve for interview**.
4. **Interviewer → My Availability.** Click the grid cells to publish free slots (the seeded interviewers already have slots for the next 5 working days).
5. **Admin → Interview Scheduling → ⚡ Auto-schedule.** Candidates are matched to the earliest free slot, and load is balanced across interviewers. You can also schedule manually from the candidate page.
6. **Interviewer → Assigned Interviews → Start interview.** Rate 5 criteria with stars, choose Accepted / Rejected / On-Hold / No-Show, and add timestamped notes.
7. **Admin → candidate → Final decision.** The combined weighted score and PASS/HOLD/REJECT band are shown. Pick **Release offer**, Hold, or Reject.
8. **Candidate → Dashboard.** Shows *Offer Released* with **Accept / Decline** buttons and a downloadable offer letter.

New-candidate flow: **Register → (no auto-login) → Login → upload/paste resume → Job Openings** (sorted by High/Medium/Low match) **→ Apply.** The hidden ATS score decides pass/fail instantly; the candidate only sees "cleared" or "not shortlisted".

---

## 4. Features vs. requirements

**Authentication**
- One landing page with *Login as Admin / Interviewer / Candidate*. Each role has its own login page.
- All logins are verified against the DB; wrong details show "Invalid credentials".
- A single master admin is hard-coded in config and bcrypt-hashed into the DB at startup.
- Admin creates, edits, deactivates and deletes interviewers and resets their passwords. Admin can **view** candidates but cannot manage them.
- Candidate self-registration requires unique email + mobile, checked in code **and** enforced by DB `UNIQUE` constraints. After registering, the candidate sees the success message and a "Login as Candidate" button; there is no auto-login.
- Forgot password leads to a reset page (email + new + confirm). It updates `password_hash` in the DB, shows "Password Reset Successful", and requires a manual login. There is no OTP, as specified.
- JWT carries `sub`, `email`, `role`. **Every protected API checks the role on the backend** (`security.require_role`). Interviewers only see their own candidates, and candidates only see their own applications.
- Logout clears the token, and protected routes redirect to login.

**AI & scoring**
- `backend/app/llm/llm_client.py` exposes one function, `call(prompt, schema)`. It supports OpenAI, Anthropic, or any OpenAI-compatible API (Groq, Gemini, Ollama…), configured in `.env`.
- There are exactly two single-turn prompts in `llm/prompts.py`:
  - `resume_match`, which returns `{score 0-100, matched_skills, gaps, summary}`
  - `answer_score`, which returns `{score 0-5, justification, confidence 0-1, rubric_hits}`
- Strict JSON validation with **at most one retry** (invalid JSON / 4xx / 5xx), then a clean failure.
- **No API key? It still works.** `LLM_PROVIDER=mock` uses a deterministic keyword scorer with the same output shape. If a real LLM fails twice, it falls back to that scorer and flags the result as `LLM_FALLBACK`.
- Fusion: weighted average of resume / assessment / interview (weights set per JD, normalised over the stages completed so far) gives a PASS / HOLD / REJECT band.
- Auto-flags: average confidence below the cutoff, resume vs Q&A disagreement ≥ 35 points, tab switches, paste/copy attempts, full-screen exits, and timeouts.
- Candidates never receive scores, justifications, flags or prompts. The serializer `candidate_app_view` strips them.

**Other**
- Audit log for every action.
- Stubbed notifications: `[NOTIFY]` lines in the backend console and toast messages in the UI. No real email or SMS is sent.

---

## 5. Using a real LLM

Edit `backend/.env`:
```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```
Free option (Groq):
```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.1-8b-instant
```
Restart the backend. The startup banner and the Admin dashboard show which AI engine is active.

## 6. Using the official `Input_Data.json`

Replace `backend/data/Input_Data.json` with the official file. The loader (`app/seed.py`) accepts common key variants:
- `job_descriptions` / `jds` / `jobs`
- `questions` with `jd_id` / `role` and `rubric`
- `users` with `name`, `email`, `password`, `role`
- `resumes` with `candidate_email` / `candidate_id` / `name` and `resume_text` / `text`

If its keys are named differently, adjust the `_get(...)` calls in `seed.py`. Admin users in the JSON are ignored because the system has exactly one admin; set `SEED_JSON_ADMINS=true` to load them too.

---

## 7. Project structure
```
smarthire/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            FastAPI app, startup seeding, serves frontend/dist in Docker
│  │  ├─ config.py          .env settings, master admin
│  │  ├─ database.py        SQLAlchemy engine (in-memory StaticPool)
│  │  ├─ models.py          User, JobDescription, Question, Application, AssessmentAnswer,
│  │  │                     AvailabilitySlot, Evaluation, Note, AuditLog
│  │  ├─ schemas.py         Pydantic request validation
│  │  ├─ security.py        bcrypt, JWT, role guards
│  │  ├─ seed.py            Input_Data.json loader
│  │  ├─ llm/               llm_client.call(), 2 prompts, heuristic fallback
│  │  ├─ services/          scoring + fusion + flags, scheduler, serializers, audit
│  │  └─ routers/           auth, admin, interviewer, candidate
│  ├─ data/Input_Data.json  3 JDs, 18 questions, 10 resumes, users
│  ├─ requirements.txt
│  └─ .env / .env.example
├─ frontend/
│  ├─ vite.config.js        /api proxy -> :8000
│  └─ src/
│     ├─ api.js             fetch wrapper + JWT
│     ├─ context.jsx        auth + toasts
│     ├─ components/        layout, protected route, UI kit
│     └─ pages/public | admin | interviewer | candidate (Assessment.jsx = proctored OA)
├─ Dockerfile
└─ start-*.bat / start-*.sh
```

## 8. Main API endpoints
| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login` · `/register` · `/reset-password` · `GET /me` · `POST /logout` |
| Admin | `/api/admin/stats` · `interviewers` (CRUD) · `candidates` (read) · `jobs` (CRUD, `batch-score`, `questions`) · `applications` (list/detail, `review`, `schedule`, `decision`, `notes`, `next-steps`, `rescore`) · `schedule/auto` · `audit-logs` |
| Interviewer | `/api/interviewer/availability` · `interviews` · `interviews/{id}/evaluation` · `/status` · `/notes` |
| Candidate | `/api/candidate/profile` · `resume` · `jobs` · `jobs/{id}/apply` · `applications` · `assessment/{start,next,answer,submit,telemetry}` · `offer-response` · `offer-letter` |

## 9. Known limits
- Resume upload accepts `.txt`/`.md` or pasted text. PDF parsing is deliberately left out, per the hackathon guardrail.
- Password reset has no OTP or email check, per the brief. Add verification before any real deployment.
- Browser-side anti-cheat can be bypassed by a determined user. It records signals for the admin; it doesn't guarantee integrity.
