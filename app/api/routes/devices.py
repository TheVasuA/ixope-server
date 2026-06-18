"""
Device management routes — heartbeat, status tracking.
Uses Redis for real-time online status (TTL-based).
"""
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.redis import set_device_online, is_device_online, get_device_status
from app.models.device import Device
from app.models.capture import ImageCapture, VideoCapture
from app.schemas.device import DeviceHeartbeat, DeviceResponse

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("/heartbeat")
async def device_heartbeat(data: DeviceHeartbeat, db: AsyncSession = Depends(get_db)):
    """
    Called by the IXOPE device every ~30s to report it's online.
    Stores real-time status in Redis (60s TTL) + updates DB last_seen.
    """
    # Redis: set device online with 60s TTL
    await set_device_online(data.device_id, data.ip_address or "", ttl=60)

    # DB: update or create device record
    result = await db.execute(select(Device).where(Device.device_id == data.device_id))
    device = result.scalar_one_or_none()

    if device:
        device.is_online = True
        device.last_seen = datetime.now(timezone.utc)
        device.ip_address = data.ip_address or device.ip_address
    else:
        device = Device(
            device_id=data.device_id,
            name=f"IXOPE-{data.device_id}",
            ip_address=data.ip_address or "",
            is_online=True,
            last_seen=datetime.now(timezone.utc),
        )
        db.add(device)

    await db.commit()
    return {"status": "ok", "device_id": data.device_id}


@router.get("", response_model=List[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db)):
    """List all registered devices with real-time online status from Redis."""
    result = await db.execute(select(Device).order_by(Device.last_seen.desc()))
    devices = result.scalars().all()

    # Enrich with real-time Redis status
    for device in devices:
        device.is_online = await is_device_online(device.device_id)

    return devices


@router.get("/{device_id}")
async def get_device_status_endpoint(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get device status — real-time from Redis + stats from DB."""
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(404, "Device not found")

    # Real-time status from Redis
    device.is_online = await is_device_online(device_id)
    redis_status = await get_device_status(device_id)

    # Get counts
    img_result = await db.execute(
        select(func.count(ImageCapture.id)).where(ImageCapture.device_id == device_id)
    )
    vid_result = await db.execute(
        select(func.count(VideoCapture.id)).where(VideoCapture.device_id == device_id)
    )

    return {
        "device": DeviceResponse.model_validate(device),
        "realtime": redis_status,
        "stats": {
            "images": img_result.scalar() or 0,
            "videos": vid_result.scalar() or 0,
        },
    }
