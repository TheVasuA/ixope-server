"""
PDF report generation — uses Redis to pre-cache selected images for instant PDF generation.

Flow:
  1. Frontend selects images → POST /api/reports/prepare (caches image data in Redis)
  2. Frontend requests PDF → POST /api/reports/generate (reads from Redis cache, instant)
"""
import os
import base64
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from app.core.database import get_db
from app.core.redis import cache_image_for_pdf, get_cached_image, cache_selected_images, get_selected_images
from app.models.capture import ImageCapture

router = APIRouter(prefix="/reports", tags=["Reports"])


class PrepareRequest(BaseModel):
    user_id: str
    image_ids: List[int]


class GenerateRequest(BaseModel):
    user_id: str
    patient_name: str
    patient_id: str
    date_of_birth: Optional[str] = ""
    notes: Optional[str] = ""


@router.post("/prepare")
async def prepare_report(data: PrepareRequest, db: AsyncSession = Depends(get_db)):
    """
    Pre-cache selected images in Redis for fast PDF generation.
    Call this when user selects images — by the time they click 'Generate',
    images are already in Redis memory (no disk reads needed).
    """
    # Fetch image records
    result = await db.execute(
        select(ImageCapture).where(ImageCapture.id.in_(data.image_ids))
    )
    images = result.scalars().all()

    cached_count = 0
    for img in images:
        if os.path.exists(img.file_path):
            with open(img.file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                await cache_image_for_pdf(img.id, b64, ttl=300)
                cached_count += 1

    # Cache the selection list
    await cache_selected_images(data.user_id, data.image_ids, ttl=600)

    return {
        "status": "success",
        "cached": cached_count,
        "total": len(data.image_ids),
        "message": f"{cached_count} images pre-cached for instant PDF generation",
    }


@router.post("/generate")
async def generate_report(data: GenerateRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate PDF report instantly using pre-cached images from Redis.
    Returns the PDF file as a downloadable stream.
    """
    # Get cached selection
    image_ids = await get_selected_images(data.user_id)
    if not image_ids:
        raise HTTPException(400, "No images prepared. Call /api/reports/prepare first.")

    # Fetch image metadata from DB
    result = await db.execute(
        select(ImageCapture).where(ImageCapture.id.in_(image_ids))
    )
    images = result.scalars().all()

    if not images:
        raise HTTPException(404, "No images found")

    # Generate PDF using ReportLab or simple approach
    pdf_bytes = await _build_pdf(images, data)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=ixope_report_{data.patient_id}.pdf"},
    )


async def _build_pdf(images: list, data: GenerateRequest) -> bytes:
    """Build PDF bytes — reads images from Redis cache (fast) with disk fallback."""
    from PIL import Image as PILImage
    from io import BytesIO as BIO

    # Simple PDF construction using reportlab-like approach
    # Using basic approach: create pages with images
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm

        buffer = BIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(20 * mm, height - 20 * mm, "IXOPE Medical Report")

        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, height - 30 * mm, f"Patient: {data.patient_name}")
        c.drawString(20 * mm, height - 36 * mm, f"ID: {data.patient_id}")
        if data.date_of_birth:
            c.drawString(20 * mm, height - 42 * mm, f"DOB: {data.date_of_birth}")
        if data.notes:
            c.drawString(20 * mm, height - 48 * mm, f"Notes: {data.notes}")

        # Images grid (2 per row)
        y_start = height - 65 * mm
        img_w, img_h = 80 * mm, 60 * mm
        margin = 15 * mm
        images_per_page = 4
        col_gap = 10 * mm

        for i, img in enumerate(images):
            if i > 0 and i % images_per_page == 0:
                c.showPage()
                y_start = height - 20 * mm

            pos = i % images_per_page
            row = pos // 2
            col = pos % 2

            x = margin + col * (img_w + col_gap)
            y = y_start - row * (img_h + 20 * mm)

            # Try Redis cache first, then disk
            b64_data = await get_cached_image(img.id)
            if b64_data:
                img_bytes = base64.b64decode(b64_data)
            elif os.path.exists(img.file_path):
                with open(img.file_path, "rb") as f:
                    img_bytes = f.read()
            else:
                # Skip missing image
                c.setFont("Helvetica", 8)
                c.drawString(x, y, f"[Image unavailable: {img.filename}]")
                continue

            # Draw image
            img_buffer = BIO(img_bytes)
            try:
                c.drawImage(
                    img_buffer, x, y - img_h, width=img_w, height=img_h,
                    preserveAspectRatio=True, anchor='c'
                )
            except Exception:
                c.drawString(x, y, f"[Cannot render: {img.filename}]")

            # Caption
            c.setFont("Helvetica", 7)
            c.drawString(x, y - img_h - 4 * mm, f"{img.scope.upper()} - {img.filename}")

        c.save()
        return buffer.getvalue()

    except ImportError:
        # Fallback: return a simple text-based response if reportlab not installed
        raise HTTPException(
            501,
            "PDF generation requires 'reportlab'. Install with: pip install reportlab"
        )
