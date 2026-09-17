"""
JWT authentication utilities.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .config import settings
from .database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def _decode_token(token: str) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise credentials_exception


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Dependency: extract a *user* (human account) from the JWT token."""
    from app.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = _decode_token(token)
    # A device token must not be usable as a user token.
    if payload.get("type") == "device":
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def require_admin(current_user=Depends(get_current_user)):
    """Dependency: only allow users with the admin role."""
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_device(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Dependency: extract a *device* from a device-scoped JWT token.

    Device tokens are minted by /auth/device/login and carry
    {"sub": <device_id>, "type": "device"}. This lets a device see only its
    own captures.
    """
    from app.models.device import Device

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid device credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = _decode_token(token)
    if payload.get("type") != "device":
        raise credentials_exception
    device_id = payload.get("sub")
    if not device_id:
        raise credentials_exception

    result = await db.execute(select(Device).where(Device.device_id == str(device_id)))
    device = result.scalar_one_or_none()

    if device is None or not device.is_active:
        raise credentials_exception

    return device


async def optional_device_id(token: str = Depends(oauth2_scheme)) -> Optional[str]:
    """Return the device_id if the request carries a valid device token, else None.

    Used to *enforce* per-device scoping on capture listings without breaking
    unauthenticated/admin/portal access. Never raises — a missing or non-device
    token simply yields None.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        return None
    if payload.get("type") != "device":
        return None
    return payload.get("sub")
