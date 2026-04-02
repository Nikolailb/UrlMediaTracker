import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine
from models import check_log, item, user  # noqa: F401 — registers all ORM models with Base
from models.base import Base
from routers import items, patterns, users
from services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating DB tables and starting scheduler.")
    Base.metadata.create_all(bind=engine)
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
app.include_router(users.router)
app.include_router(patterns.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": app.version}
