"""
Admin routes — dashboard stats, device management, user management.

All endpoints here require an authenticated admin (see require_admin).
Registering a device auto-creates login credentials for it so the device can
log in independently and see only its own captures. Deleting a device or user
cascades to their images/videos (DB rows + files on disk).
"""
import secrets
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.core.database import get_db
from app.core.auth import require_admin, hash_password
from app.models.capture import ImageCapture, VideoCapture
from app.models.device import Device
from app.models.user import User
from app.schemas.device import (
    DeviceResponse,
    DeviceRegisterRequest,
    DeviceCredentialsResponse,
)
from app.services.cleanup import remove_capture_files
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["Admin"])


# ─── Stats ───────────────────────────────────────────────────────────────────
@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db), _admin=Depends(require_admin)):
    """Get admin dashboard stats — totals across all devices."""
    img_count = (await db.execute(select(func.count(ImageCapture.id)))).scalar() or 0
    vid_count = (await db.execute(select(func.count(VideoCapture.id)))).scalar() or 0
    device_count = (await db.execute(select(func.count(Device.id)))).scalar() or 0

    scope_stats = []
    for scope in ['opth', 'oto', 'derm', 'micro']:
        imgs = (await db.execute(
            select(func.count(ImageCapture.id)).where(ImageCapture.scope == scope)
        )).scalar() or 0
        vids = (await db.execute(
            select(func.count(VideoCapture.id)).where(VideoCapture.scope == scope)
        )).scalar() or 0
        scope_stats.append({"scope": scope, "images": imgs, "videos": vids})

    recent_imgs = (await db.execute(
        select(ImageCapture).order_by(ImageCapture.captured_at.desc()).limit(10)
    )).scalars().all()

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


# ─── Device management ─────────────────────────────────────────────────────────
def _next_device_id(existing_ids: List[str]) -> str:
    """Pick the next numeric device id, starting at 1002 (1001 is the demo)."""
    nums = []
    for did in existing_ids:
        try:
            nums.append(int(did))
        except (TypeError, ValueError):
            continue
    return str((max(nums) if nums else 1001) + 1)


@router.get("/devices", response_model=List[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db), _admin=Depends(require_admin)):
    """List all devices (with usernames, without password hashes)."""
    result = await db.execute(select(Device).order_by(Device.created_at.desc()))
    return result.scalars().all()


@router.post("/devices", response_model=DeviceCredentialsResponse, status_code=201)
async def register_device(
    data: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Register a device and auto-create its login credentials.

    Returns the plaintext password ONCE so the admin can hand it to the device
    operator. The password is stored only as a bcrypt hash.
    """
    existing_ids = [
        d for (d,) in (await db.execute(select(Device.device_id))).all()
    ]

    device_id = (data.device_id or "").strip() or _next_device_id(existing_ids)

    # Ensure device_id is unique
    dup = await db.execute(select(Device).where(Device.device_id == device_id))
    device = dup.scalar_one_or_none()

    username = (data.username or "").strip() or f"device_{device_id}"

    # Ensure username is unique across devices
    uname_dup = await db.execute(
        select(Device).where(Device.username == username, Device.device_id != device_id)
    )
    if uname_dup.scalar_one_or_none():
        raise HTTPException(409, f"Username '{username}' already in use")

    password = (data.password or "").strip() or secrets.token_urlsafe(9)
    name = (data.name or "").strip() or f"IXOPE-{device_id}"

    if device:
        # Device already exists (e.g. created by a heartbeat) — attach credentials.
        device.name = name
        device.username = username
        device.hashed_password = hash_password(password)
        device.is_active = True
    else:
        device = Device(
            device_id=device_id,
            name=name,
            ip_address="",
            is_online=False,
            username=username,
            hashed_password=hash_password(password),
            is_active=True,
        )
        db.add(device)

    await db.commit()
    await db.refresh(device)

    return DeviceCredentialsResponse(
        device_id=device.device_id,
        name=device.name,
        username=device.username,
        password=password,
    )


@router.post("/devices/{device_id}/reset-credentials", response_model=DeviceCredentialsResponse)
async def reset_device_credentials(
    device_id: str,
    data: DeviceRegisterRequest = None,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Reset a device's password (and optionally username). Returns new plaintext password once."""
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")

    data = data or DeviceRegisterRequest()
    new_username = (data.username or "").strip() or device.username or f"device_{device_id}"

    if new_username != device.username:
        uname_dup = await db.execute(
            select(Device).where(Device.username == new_username, Device.device_id != device_id)
        )
        if uname_dup.scalar_one_or_none():
            raise HTTPException(409, f"Username '{new_username}' already in use")

    new_password = (data.password or "").strip() or secrets.token_urlsafe(9)
    device.username = new_username
    device.hashed_password = hash_password(new_password)
    device.is_active = True
    await db.commit()
    await db.refresh(device)

    return DeviceCredentialsResponse(
        device_id=device.device_id,
        name=device.name,
        username=device.username,
        password=new_password,
    )


async def _delete_device_media(device_id: str, db: AsyncSession) -> dict:
    """Delete all image/video captures for a device — DB rows + files on disk."""
    images = (await db.execute(
        select(ImageCapture).where(ImageCapture.device_id == device_id)
    )).scalars().all()
    videos = (await db.execute(
        select(VideoCapture).where(VideoCapture.device_id == device_id)
    )).scalars().all()

    for img in images:
        remove_capture_files(img.file_path, img.thumbnail_path, img.id)
        await db.delete(img)
    for vid in videos:
        remove_capture_files(vid.file_path, vid.thumbnail_path, vid.id)
        await db.delete(vid)

    return {"images": len(images), "videos": len(videos)}


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Delete a device AND all of its images/videos (files + DB rows)."""
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")

    deleted = await _delete_device_media(device_id, db)
    await db.delete(device)
    await db.commit()

    return {
        "status": "success",
        "message": f"Device {device_id} and its media deleted",
        "deleted_images": deleted["images"],
        "deleted_videos": deleted["videos"],
    }


# ─── User management ───────────────────────────────────────────────────────────
class AdminUserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class AdminCreateUserRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: Optional[str] = ""
    role: Optional[str] = "doctor"


@router.get("/users", response_model=List[AdminUserResponse])
async def list_users(db: AsyncSession = Depends(get_db), _admin=Depends(require_admin)):
    """List all human user accounts."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_user(
    data: AdminCreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Create a new user account."""
    existing = await db.execute(
        select(User).where(or_(User.email == data.email, User.username == data.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email or username already exists")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name or "",
        role=data.role or "doctor",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    """Delete a user account. An admin cannot delete their own account."""
    if admin.id == user_id:
        raise HTTPException(400, "You cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    await db.delete(user)
    await db.commit()
    return {"status": "success", "message": f"User {user_id} deleted"}
