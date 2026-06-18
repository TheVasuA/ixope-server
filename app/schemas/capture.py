from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ImageResponse(BaseModel):
    id: int
    device_id: str
    patient_id: Optional[str] = None
    scope: str
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    notes: str
    url: str = ""
    thumbnail_url: str = ""
    captured_at: Optional[datetime] = None
    uploaded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VideoResponse(BaseModel):
    id: int
    device_id: str
    patient_id: Optional[str] = None
    scope: str
    filename: str
    original_filename: str
    file_size: int
    duration_seconds: int
    mime_type: str
    notes: str
    url: str = ""
    thumbnail_url: str = ""
    captured_at: Optional[datetime] = None
    uploaded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    status: str
    message: str
    filename: str
    id: int
