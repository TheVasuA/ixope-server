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
        data.url = f"/api/videos/{vid.id}/file"
        response.append(data)

    return response


@router.get("/{video_id}/file")
async def get_video_file(video_id: int, db: AsyncSession = Depends(get_db)):
    """Serve video file with range request support."""
    result = await db.execute(select(VideoCapture).where(VideoCapture.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(404, "Video not found")

    import os
    if not os.path.exists(video.file_path):
        raise HTTPException(404, "File not found on disk")

    return FileResponse(video.file_path, media_type=video.mime_type, filename=video.filename)


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
