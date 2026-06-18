"""
Capture upload routes — handles image/video uploads from IXOPE devices and web portal.

Standard endpoints:
  POST /api/captures/images   — Upload an image
  POST /api/captures/videos   — Upload a video
"""
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.models.capture import ImageCapture, VideoCapture
from app.schemas.capture import UploadResponse
from app.services.thumbnail import generate_image_thumbnail, generate_video_thumbnail

router = APIRouter(prefix="/captures", tags=["Captures"])

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
ALLOWED_VIDEO_EXT = {".mp4", ".avi", ".mov", ".webm", ".mkv"}


def _generate_filename(original: str, device_id: str, prefix: str) -> str:
    """Generate unique filename: prefix_deviceid_timestamp_uuid.ext"""
    ext = os.path.splitext(original)[1].lower()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"{prefix}_{device_id}_{ts}_{uid}{ext}"


@router.post("/images", response_model=UploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    device_id: str = Query(..., alias="id", description="Device ID"),
    scope: str = Query("general", description="Scope: opth, oto, derm, micro"),
    patient_id: str = Query("", description="Patient ID (optional)"),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image capture."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"Invalid image format: {ext}. Allowed: {ALLOWED_IMAGE_EXT}")

    filename = _generate_filename(file.filename, device_id, "img")
    save_dir = os.path.join(settings.UPLOAD_DIR, "images", scope)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    content = await file.read()
    file_size = len(content)

    if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")

    with open(save_path, "wb") as f:
        f.write(content)

    # Generate thumbnail
    thumb_path = generate_image_thumbnail(save_path, settings.UPLOAD_DIR) or ""

    image = ImageCapture(
        device_id=device_id,
        patient_id=patient_id or None,
        scope=scope,
        filename=filename,
        original_filename=file.filename,
        file_path=save_path,
        thumbnail_path=thumb_path,
        file_size=file_size,
        mime_type=file.content_type or "image/jpeg",
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)

    return UploadResponse(
        status="success",
        message="Image uploaded successfully",
        filename=filename,
        id=image.id,
    )


@router.post("/videos", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    device_id: str = Query(..., alias="id", description="Device ID"),
    scope: str = Query("general", description="Scope: opth, oto, derm, micro"),
    patient_id: str = Query("", description="Patient ID (optional)"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a video capture."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(400, f"Invalid video format: {ext}. Allowed: {ALLOWED_VIDEO_EXT}")

    filename = _generate_filename(file.filename, device_id, "vid")
    save_dir = os.path.join(settings.UPLOAD_DIR, "videos", scope)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    content = await file.read()
    file_size = len(content)

    if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")

    with open(save_path, "wb") as f:
        f.write(content)

    # Generate video poster thumbnail
    thumb_path = generate_video_thumbnail(save_path, settings.UPLOAD_DIR) or ""

    video = VideoCapture(
        device_id=device_id,
        patient_id=patient_id or None,
        scope=scope,
        filename=filename,
        original_filename=file.filename,
        file_path=save_path,
        thumbnail_path=thumb_path,
        file_size=file_size,
        mime_type=file.content_type or "video/mp4",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    return UploadResponse(
        status="success",
        message="Video uploaded successfully",
        filename=filename,
        id=video.id,
    )
