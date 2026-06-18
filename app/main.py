"""
IXOPE Server — FastAPI backend for medical image/video management.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import init_db
from app.core.redis import get_redis, close_redis
from app.api.routes import upload, images, videos, devices, patients, stats, pdf


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + connect Redis. Shutdown: cleanup."""
    await init_db()
    await get_redis()  # Warm up Redis connection
    yield
    await close_redis()


app = FastAPI(
    title="IXOPE Medical Server",
    description="Backend API for IXOPE medical imaging device — manages image/video uploads, patients, and device connections.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for uploads
app.mount("/files", StaticFiles(directory=settings.UPLOAD_DIR), name="files")

# API routes — no /api prefix, subdomain IS the api
app.include_router(upload.router)
app.include_router(images.router)
app.include_router(videos.router)
app.include_router(stats.router)
app.include_router(devices.router)
app.include_router(patients.router)
app.include_router(pdf.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "ixope-server"}
