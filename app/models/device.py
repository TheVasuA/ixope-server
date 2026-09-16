from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.core.database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), default="")
    ip_address = Column(String(45), default="")
    is_online = Column(Boolean, default=False)

    # ─── Login credentials (auto-created by admin on registration) ───────────
    # Each device gets its own username/password so it can log in independently
    # and only see its own captures.
    username = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
