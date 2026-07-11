from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.backend.api import chapters, jobs, novels, policies
from web.backend.config import settings
from web.backend.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Seed is now idempotent — run manually via: uv run python -m web.backend.seed
    # from web.backend.seed import seed
    # await seed()
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
app.include_router(jobs.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
