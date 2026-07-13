from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.backend.api import chapters, jobs, novels, policies, style
from web.backend.config import settings
from web.backend.db.database import init_db

os.makedirs("logs", exist_ok=True)
file_handler = RotatingFileHandler("logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=5)
console_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[file_handler, console_handler],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from sqlalchemy import update

    from web.backend.db.database import async_session
    from web.backend.db.models import Chapter, ProcessingJob

    active_statuses = [
        "processing",
        "queued",
        "cleaning",
        "applying_rules",
        "rewriting",
        "validating",
        "extracting_lore",
        "extracting",
    ]

    async with async_session() as session:
        # Reset stuck chapters
        await session.execute(
            update(Chapter)
            .where(Chapter.status.in_(active_statuses))
            .values(status="failed", error_message="Processing interrupted by server restart.")
        )
        # Reset stuck jobs
        await session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.status.in_(["running", "queued"]))
            .values(status="failed", error_message="Processing interrupted by server restart.")
        )
        await session.commit()

    yield


app = FastAPI(
    title="Translator Memory Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(novels.router)
app.include_router(chapters.router)
app.include_router(policies.router)
app.include_router(style.router)
app.include_router(jobs.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
