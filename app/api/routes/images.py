"""
Image retrieval routes — query images by device, patient, scope, date range.
"""
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.config import settings
from app.models.capture import ImageCapture
from app.schemas.capture import ImageResponse

router = APIRouter(prefix="/captures/images", tags=["Images"])


@router.get("", response_model=List[ImageResponse])
async def list_images(
    device_id: str = Query("", description="Filter by device ID"),
    patient_id: str = Query("", description="Filter by patient ID"),
    scope: str = Query("", description="Filter by scope: opth, oto, derm, micro"),
    date_from: Optional[date] = Query(None, description="From date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="To date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List images with flexible filtering."""
    conditions = []

    if device_id:
        conditions.append(ImageCapture.device_id == device_id)
    if patient_id:
        conditions.append(ImageCapture.patient_id == patient_id)
    if scope:
        conditions.append(ImageCapture.scope == scope)
    if date_from:
        conditions.append(ImageCapture.captured_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        conditions.append(ImageCapture.captured_at <= datetime.combine(date_to, datetime.max.time()))

    query = (
        select(ImageCapture)
        .where(and_(*conditions) if conditions else True)
        .order_by(ImageCapture.captured_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    images = result.scalars().all()

    # Add URL field
    response = []
    for img in images:
        data = ImageResponse.model_validate(img)
        data.url = f"/captures/images/{img.id}/file"
        data.thumbnail_url = f"/captures/images/{img.id}/thumbnail"
        response.append(data)

    return response


@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """Get image metadata by ID."""
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")
    data = ImageResponse.model_validate(image)
    data.url = f"/api/images/{image.id}/file"
    return data


@router.get("/{image_id}/file")
async def get_image_file(image_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the actual image file."""
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")

    import os
    if not os.path.exists(image.file_path):
        raise HTTPException(404, "File not found on disk")

    return FileResponse(image.file_path, media_type=image.mime_type, filename=image.filename)


@router.get("/{image_id}/thumbnail")
async def get_image_thumbnail(image_id: int, db: AsyncSession = Depends(get_db)):
    """Serve image thumbnail (small, fast-loading for grids)."""
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")

    import os
    # Serve thumbnail if available, otherwise serve original
    if image.thumbnail_path and os.path.exists(image.thumbnail_path):
        return FileResponse(image.thumbnail_path, media_type="image/jpeg")

    if os.path.exists(image.file_path):
        return FileResponse(image.file_path, media_type=image.mime_type)

    raise HTTPException(404, "File not found")


@router.delete("/{image_id}")
async def delete_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an image."""
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")

    import os
    if os.path.exists(image.file_path):
        os.remove(image.file_path)

    await db.delete(image)
    await db.commit()
    return {"status": "success", "message": f"Image {image_id} deleted"}
