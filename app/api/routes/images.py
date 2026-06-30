"""
Image retrieval routes — query images by device, patient, scope, date range.
"""
import os
import re
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse, Response
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

    return FileResponse(
        image.file_path,
        media_type=image.mime_type,
        filename=image.filename,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/{image_id}/dicom")
async def get_image_dicom(
    image_id: int,
    patient_name: str = Query("", description="Override patient name for DICOM tags"),
    patient_id: str = Query("", description="Override patient ID for DICOM tags"),
    date_of_birth: str = Query("", description="Patient DOB (YYYY-MM-DD)"),
    patient_sex: str = Query("", description="Patient sex (M/F/O)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Convert a stored capture to a DICOM Secondary Capture (.dcm) file on the
    server and stream it back. Conversion uses pydicom and produces an
    uncompressed RGB file that opens in any standard DICOM viewer.
    """
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")
    if not os.path.exists(image.file_path):
        raise HTTPException(404, "File not found on disk")

    # Defer import so the rest of the API works even if pydicom isn't installed.
    try:
        from app.services.dicom import jpeg_to_dicom
    except ImportError:
        raise HTTPException(
            501, "DICOM conversion requires 'pydicom'. Install with: pip install pydicom Pillow"
        )

    with open(image.file_path, "rb") as f:
        image_bytes = f.read()

    # Notes may embed a body-part marker, e.g. "[body_part:hand] clinical text"
    raw_notes = image.notes or ""
    bp_match = re.search(r"\[body_part:(\w+)\]", raw_notes)
    body_part = bp_match.group(1) if bp_match else ""
    clean_notes = re.sub(r"\[body_part:\w+\]\s*", "", raw_notes).strip()

    dcm_bytes = jpeg_to_dicom(
        image_bytes,
        patient_name=patient_name or (image.patient_id or "Anonymous"),
        patient_id=patient_id or (image.patient_id or ""),
        date_of_birth=date_of_birth,
        patient_sex=patient_sex,
        scope=image.scope or "",
        body_part=body_part,
        notes=clean_notes,
        captured_at=image.captured_at,
    )

    base = os.path.splitext(image.original_filename or image.filename)[0]
    download_name = f"{base or f'image_{image_id}'}.dcm"

    return Response(
        content=dcm_bytes,
        media_type="application/dicom",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{image_id}/thumbnail")
async def get_image_thumbnail(image_id: int, db: AsyncSession = Depends(get_db)):
    """Serve image thumbnail (small, fast-loading for grids)."""
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")

    import os
    cors_headers = {"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=86400"}

    # Serve thumbnail if available, otherwise serve original
    if image.thumbnail_path and os.path.exists(image.thumbnail_path):
        return FileResponse(image.thumbnail_path, media_type="image/jpeg", headers=cors_headers)

    if os.path.exists(image.file_path):
        return FileResponse(image.file_path, media_type=image.mime_type, headers=cors_headers)

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


@router.patch("/{image_id}/notes")
async def update_image_notes(image_id: int, db: AsyncSession = Depends(get_db), notes: str = Query(..., description="Clinical notes for this image")):
    """Update notes/description for an image."""
    result = await db.execute(select(ImageCapture).where(ImageCapture.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Image not found")

    image.notes = notes
    await db.commit()
    await db.refresh(image)
    return {"status": "success", "message": "Notes updated", "id": image_id, "notes": image.notes}
