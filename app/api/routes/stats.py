"""
Stats route — get image/video counts per scope.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.models.capture import ImageCapture, VideoCapture

router = APIRouter(prefix="/captures", tags=["Stats"])


@router.get("/stats")
async def get_scope_stats(
    device_id: str = Query("", description="Device ID"),
    scope: str = Query("", description="Scope category"),
    db: AsyncSession = Depends(get_db),
):
    """Get image and video counts for a device/scope."""
    # Image count
    img_q = select(func.count(ImageCapture.id))
    if device_id:
        img_q = img_q.where(ImageCapture.device_id == device_id)
    if scope:
        img_q = img_q.where(ImageCapture.scope == scope)
    img_result = await db.execute(img_q)

    # Video count
    vid_q = select(func.count(VideoCapture.id))
    if device_id:
        vid_q = vid_q.where(VideoCapture.device_id == device_id)
    if scope:
        vid_q = vid_q.where(VideoCapture.scope == scope)
    vid_result = await db.execute(vid_q)

    return {
        "scope": scope or "all",
        "images": img_result.scalar() or 0,
        "videos": vid_result.scalar() or 0,
    }
