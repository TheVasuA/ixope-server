"""
Admin routes — dashboard stats, user management.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.models.capture import ImageCapture, VideoCapture
from app.models.device import Device

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)):
    """Get admin dashboard stats — totals across all devices."""
    img_count = (await db.execute(select(func.count(ImageCapture.id)))).scalar() or 0
    vid_count = (await db.execute(select(func.count(VideoCapture.id)))).scalar() or 0
    device_count = (await db.execute(select(func.count(Device.id)))).scalar() or 0

    # Per-scope breakdown
    scope_stats = []
    for scope in ['opth', 'oto', 'derm', 'micro']:
        imgs = (await db.execute(
            select(func.count(ImageCapture.id)).where(ImageCapture.scope == scope)
        )).scalar() or 0
        vids = (await db.execute(
            select(func.count(VideoCapture.id)).where(VideoCapture.scope == scope)
        )).scalar() or 0
        scope_stats.append({"scope": scope, "images": imgs, "videos": vids})

    # Recent images (last 10)
    recent_imgs = (await db.execute(
        select(ImageCapture).order_by(ImageCapture.captured_at.desc()).limit(10)
    )).scalars().all()

    # Storage size
    total_img_size = (await db.execute(select(func.sum(ImageCapture.file_size)))).scalar() or 0
    total_vid_size = (await db.execute(select(func.sum(VideoCapture.file_size)))).scalar() or 0

    return {
        "total_images": img_count,
        "total_videos": vid_count,
        "total_devices": device_count,
        "total_storage_bytes": total_img_size + total_vid_size,
        "scope_stats": scope_stats,
        "recent_images": [
            {
                "id": img.id,
                "scope": img.scope,
                "filename": img.original_filename or img.filename,
                "device_id": img.device_id,
                "captured_at": img.captured_at.isoformat() if img.captured_at else None,
            }
            for img in recent_imgs
        ],
    }
