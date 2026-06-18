from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Text, func
from app.core.database import Base


class ImageCapture(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True, nullable=False)
    patient_id = Column(String(50), ForeignKey("patients.patient_id"), nullable=True, index=True)
    scope = Column(String(20), index=True, nullable=False)  # opth, oto, derm, micro
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), default="")
    file_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500), default="")
    file_size = Column(BigInteger, default=0)
    mime_type = Column(String(50), default="image/jpeg")
    notes = Column(Text, default="")
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())


class VideoCapture(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True, nullable=False)
    patient_id = Column(String(50), ForeignKey("patients.patient_id"), nullable=True, index=True)
    scope = Column(String(20), index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), default="")
    file_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500), default="")
    file_size = Column(BigInteger, default=0)
    duration_seconds = Column(Integer, default=0)
    mime_type = Column(String(50), default="video/mp4")
    notes = Column(Text, default="")
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
