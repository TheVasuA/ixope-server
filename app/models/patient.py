from sqlalchemy import Column, Integer, String, Date, Text, DateTime, func
from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    patient_id = Column(String(50), unique=True, index=True, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(10), default="")
    phone = Column(String(20), default="")
    email = Column(String(100), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
