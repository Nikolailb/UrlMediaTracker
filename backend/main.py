import logging
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import SessionLocal
from models.user import LoginSession, User
from routers import archive, auth, items, patterns, tools
from services.auth import token_hash
from services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — expecting Alembic migrations to be applied.")
    start_scheduler()
    yield
    logger.info("Shutting down — stopping scheduler.")
    stop_scheduler()


app = FastAPI(
    title="Smart Bookmark & Chapter Tracker",
    description=(
        "Track progress across serialized online content. "
        "Automatically extracts chapter patterns and monitors for updates."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:4173",   # Vite preview
        "http://localhost:3000",   # optional alt dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router)
app.include_router(auth.router)
app.include_router(patterns.router)
app.include_router(tools.router)
app.include_router(archive.router)


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.url.path not in {"/auth/login", "/auth/accept-invite"}:
        token = request.cookies.get("tracker_session")
        with SessionLocal() as db:
            row = db.query(LoginSession).filter(LoginSession.token_hash == token_hash(token or "")).first()
            if not row or row.revoked_at or not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), row.csrf_token):
                return JSONResponse({"detail": "Invalid CSRF token."}, status_code=403)
    return await call_next(request)


@app.get("/health", tags=["system"])
def health():
    with SessionLocal() as db:
        if not db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True)).first():
            raise HTTPException(503, "Admin bootstrap required.")
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
