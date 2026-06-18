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
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
