from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DeviceHeartbeat(BaseModel):
    device_id: str
    ip_address: Optional[str] = ""


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    name: str
    ip_address: str
    is_online: bool
    username: Optional[str] = None
    is_active: bool = True
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DeviceRegisterRequest(BaseModel):
    """Admin registers a device. If username/password omitted, they are
    auto-generated from the device_id."""
    device_id: Optional[str] = None
    name: Optional[str] = ""
    username: Optional[str] = None
    password: Optional[str] = None


class DeviceCredentialsResponse(BaseModel):
    """Returned once on registration / credential reset so the admin can hand
    the login details to the device operator. Password is plaintext here ONLY
    because it was just generated — it is never stored or returned again."""
    device_id: str
    name: str
    username: str
    password: str


class DeviceLoginRequest(BaseModel):
    username: str
    password: str
