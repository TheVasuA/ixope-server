from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class PatientCreate(BaseModel):
    name: str
    patient_id: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    notes: Optional[str] = ""


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None


class PatientResponse(BaseModel):
    id: int
    name: str
    patient_id: str
    date_of_birth: Optional[date] = None
    gender: str
    phone: str
    email: str
    notes: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
