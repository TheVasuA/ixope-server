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
    """Build PDF — one full-page image per page, reads from Redis/disk."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
    except ImportError:
        raise HTTPException(
            501,
            "PDF generation requires 'reportlab'. Install with: pip install reportlab Pillow"
        )

    buffer = BIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 15 * mm

    # ─── Cover page ─────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, height - 25 * mm, "IXOPE Medical Report")

    c.setFont("Helvetica", 10)
    c.drawString(margin, height - 35 * mm, f"Patient: {data.patient_name}")
    c.drawString(margin, height - 41 * mm, f"ID: {data.patient_id}")
    if data.date_of_birth:
        c.drawString(margin, height - 47 * mm, f"Date of Birth: {data.date_of_birth}")

    from datetime import datetime
    c.drawString(margin, height - 55 * mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.drawString(margin, height - 61 * mm, f"Total images: {len(images)}")

    if data.notes:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, height - 73 * mm, "Notes:")
        c.setFont("Helvetica", 9)
        # Simple word wrap
        words = data.notes.split()
        line = ""
        y_pos = height - 80 * mm
        for word in words:
            if c.stringWidth(line + " " + word, "Helvetica", 9) < (width - 2 * margin):
                line += (" " + word) if line else word
            else:
                c.drawString(margin, y_pos, line)
                y_pos -= 4 * mm
                line = word
        if line:
            c.drawString(margin, y_pos, line)

    # ─── One image per page ──────────────────────────────────────────────
    for i, img in enumerate(images):
        c.showPage()

        # Title bar
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, height - 15 * mm, f"Image {i + 1} of {len(images)}")
        c.setFont("Helvetica", 9)
        c.drawString(margin, height - 21 * mm, f"{img.scope.upper()} - {img.original_filename or img.filename}")

        # Draw separator line
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.line(margin, height - 24 * mm, width - margin, height - 24 * mm)

        # Image area
        img_area_top = height - 28 * mm
        img_area_bottom = 15 * mm
        img_area_height = img_area_top - img_area_bottom
        img_area_width = width - 2 * margin

        # Get image bytes from Redis cache or disk
        b64_data = await get_cached_image(img.id)
        if b64_data:
            img_bytes = base64.b64decode(b64_data)
        elif os.path.exists(img.file_path):
            with open(img.file_path, "rb") as f:
                img_bytes = f.read()
        else:
            c.setFont("Helvetica", 12)
            c.drawString(margin, height / 2, f"Image file not found: {img.filename}")
            continue

        # Draw full-page image maintaining aspect ratio
        try:
            img_reader = ImageReader(BIO(img_bytes))
            iw, ih = img_reader.getSize()
            aspect = iw / ih

            if aspect > img_area_width / img_area_height:
                # Wider — fit by width
                draw_w = img_area_width
                draw_h = img_area_width / aspect
            else:
                # Taller — fit by height
                draw_h = img_area_height
                draw_w = img_area_height * aspect

            # Center in available area
            draw_x = margin + (img_area_width - draw_w) / 2
            draw_y = img_area_bottom + (img_area_height - draw_h) / 2

            c.drawImage(img_reader, draw_x, draw_y, width=draw_w, height=draw_h)
        except Exception as e:
            c.setFont("Helvetica", 10)
            c.drawString(margin, height / 2, f"Cannot render image: {img.filename}")
            c.drawString(margin, height / 2 - 5 * mm, f"Error: {str(e)[:80]}")

    # ─── Page numbers ────────────────────────────────────────────────────
    total_pages = c.getPageNumber()
    # ReportLab doesn't easily support retroactive page numbers,
    # so we skip that for simplicity

    c.save()
    return buffer.getvalue()
