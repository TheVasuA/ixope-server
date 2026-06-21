"""
Video retrieval routes — query videos by device, patient, scope, date range.
"""
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.models.capture import VideoCapture
from app.schemas.capture import VideoResponse

router = APIRouter(prefix="/captures/videos", tags=["Videos"])


@router.get("", response_model=List[VideoResponse])
async def list_videos(
    device_id: str = Query("", description="Filter by device ID"),
    patient_id: str = Query("", description="Filter by patient ID"),
    scope: str = Query("", description="Filter by scope"),
    date_from: Optional[date] = Query(None, description="From date"),
    date_to: Optional[date] = Query(None, description="To date"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List videos with flexible filtering."""
    conditions = []

    if device_id:
        conditions.append(VideoCapture.device_id == device_id)
    if patient_id:
        conditions.append(VideoCapture.patient_id == patient_id)
    if scope:
        conditions.append(VideoCapture.scope == scope)
    if date_from:
        conditions.append(VideoCapture.captured_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        conditions.append(VideoCapture.captured_at <= datetime.combine(date_to, datetime.max.time()))

    query = (
        select(VideoCapture)
        .where(and_(*conditions) if conditions else True)
        .order_by(VideoCapture.captured_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    videos = result.scalars().all()

    response = []
    for vid in videos:
        data = VideoResponse.model_validate(vid)
        data.url = f"/captures/videos/{vid.id}/file"
        response.append(data)

    return response


@router.get("/{video_id}/file")
async def get_video_file(video_id: int, download: str = Query("", description="Set to trigger download"), db: AsyncSession = Depends(get_db)):
    """Serve video file with optional download attachment header."""
    result = await db.execute(select(VideoCapture).where(VideoCapture.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(404, "Video not found")

    import os
    if not os.path.exists(video.file_path):
        raise HTTPException(404, "File not found on disk")

    # If download param is present, force browser to download instead of play inline
    if download:
        return FileResponse(
            video.file_path,
            media_type="application/octet-stream",
            filename=video.original_filename or video.filename,
            headers={"Content-Disposition": f'attachment; filename="{video.original_filename or video.filename}"'},
        )

    return FileResponse(
        video.file_path,
        media_type=video.mime_type or "video/mp4",
        filename=video.filename,
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/{video_id}/stream")
async def stream_video_h264(video_id: int, db: AsyncSession = Depends(get_db)):
    """
    Stream video transcoded to H.264 on-the-fly for browser playback.
    Falls back to raw file if ffmpeg is not available.
    """
    import os
    import shutil
    import asyncio
    from fastapi.responses import StreamingResponse

    result = await db.execute(select(VideoCapture).where(VideoCapture.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(404, "Video not found")

    if not os.path.exists(video.file_path):
        raise HTTPException(404, "File not found on disk")

    # Check for pre-transcoded cached version
    cache_dir = os.path.join(os.path.dirname(video.file_path), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cached_path = os.path.join(cache_dir, f"{video.id}_h264.mp4")

    if os.path.exists(cached_path):
        return FileResponse(cached_path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})

    # If ffmpeg not available, serve raw file
    if not shutil.which("ffmpeg"):
        return FileResponse(video.file_path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})

    # Transcode to cached file (one-time cost per video)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", video.file_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-movflags", "+faststart",
            cached_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0 and os.path.exists(cached_path):
            return FileResponse(cached_path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})
    except Exception:
        pass

    # Fallback: serve original
    return FileResponse(video.file_path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})


@router.delete("/{video_id}")
async def delete_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a video."""
    result = await db.execute(select(VideoCapture).where(VideoCapture.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(404, "Video not found")

    import os
    if os.path.exists(video.file_path):
        os.remove(video.file_path)

    await db.delete(video)
    await db.commit()
    return {"status": "success", "message": f"Video {video_id} deleted"}
