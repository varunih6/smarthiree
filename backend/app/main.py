"""
SmartHire Pipeline — FastAPI entry point.
Run:  uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, SessionLocal, engine
from .llm import llm_client
from .routers import admin, auth, candidate, interviewer
from .seed import load_seed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from .models import JobDescription
        if db.query(JobDescription).count() == 0:
            load_seed(db)
        else:
            from .seed import ensure_master_admin
            ensure_master_admin(db)
    finally:
        db.close()
    print(f"\n  SmartHire API ready  |  DB: {config.DATABASE_URL}  |  LLM: {llm_client.provider_label()}")
    print(f"  Master admin: {config.MASTER_ADMIN_EMAIL}\n", flush=True)
    yield


app = FastAPI(title="SmartHire Pipeline API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    # Turn pydantic errors into one friendly message for the UI
    msgs = []
    for e in exc.errors():
        field = e["loc"][-1] if e.get("loc") else ""
        msg = str(e.get("msg", "Invalid value")).replace("Value error, ", "")
        msgs.append(msg if field in ("body", "") or field in msg.lower() else f"{field}: {msg}")
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(interviewer.router)
app.include_router(candidate.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm_client.provider_label(), "db": config.DATABASE_URL}


# Optional: serve the built React app (frontend/dist) from the same server,
# used by the Docker single-container setup.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = DIST / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
