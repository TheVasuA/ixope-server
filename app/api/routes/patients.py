"""
Patient management routes.
"""
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("", response_model=PatientResponse, status_code=201)
async def create_patient(data: PatientCreate, db: AsyncSession = Depends(get_db)):
    """Register a new patient."""
    # Check if patient_id already exists
    existing = await db.execute(select(Patient).where(Patient.patient_id == data.patient_id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Patient ID '{data.patient_id}' already exists")

    patient = Patient(**data.model_dump())
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


@router.get("", response_model=List[PatientResponse])
async def list_patients(
    search: str = Query("", description="Search by name or patient ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all patients with optional search."""
    query = select(Patient).order_by(Patient.created_at.desc())

    if search:
        query = query.where(
            Patient.name.ilike(f"%{search}%") | Patient.patient_id.ilike(f"%{search}%")
        )

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Get patient by patient_id."""
    result = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(patient_id: str, data: PatientUpdate, db: AsyncSession = Depends(get_db)):
    """Update patient info."""
    result = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(404, "Patient not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(patient, key, value)

    await db.commit()
    await db.refresh(patient)
    return patient


@router.delete("/{patient_id}")
async def delete_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a patient record."""
    result = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(404, "Patient not found")

    await db.delete(patient)
    await db.commit()
    return {"status": "success", "message": f"Patient {patient_id} deleted"}
