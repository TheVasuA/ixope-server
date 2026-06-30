"""
DICOM Secondary Capture generation service.

Converts stored JPEG/PNG captures into clinically valid DICOM (.dcm) files
using pydicom (https://github.com/pydicom/pydicom), the de-facto standard
Python DICOM library.

Pixel data is written uncompressed (Explicit VR Little Endian, 8-bit
MONOCHROME2 grayscale) which is the most widely compatible encoding and
opens in any conformant DICOM viewer (OsiriX, Horos, RadiAnt, Weasis,
3D Slicer, dcm4che, etc.).
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    PYDICOM_IMPLEMENTATION_UID,
    generate_uid,
)


# Map device scope -> DICOM Modality (defined terms, PS3.3 C.7.3.1.1.1)
_MODALITY_MAP = {
    "derm": "XC",   # External-camera Photography (dermatoscopy)
    "opth": "OP",   # Ophthalmic Photography
    "oto": "XC",    # External-camera Photography
    "micro": "GM",  # General Microscopy
}

# Map body-part keyword -> DICOM Body Part Examined (PS3.16 Annex L)
_BODY_PART_MAP = {
    "arm": "ARM",
    "chest": "CHEST",
    "ears": "EAR",
    "hand": "HAND",
    "head": "HEAD",
    "foot": "FOOT",
    "leg": "LEG",
}


def _modality(scope: str) -> str:
    return _MODALITY_MAP.get((scope or "").lower(), "OT")


def _body_part(body_part: str) -> str:
    return _BODY_PART_MAP.get((body_part or "").lower(), "")


def _format_birth_date(dob: str) -> str:
    """Accept YYYY-MM-DD or YYYYMMDD, return DICOM DA (YYYYMMDD)."""
    if not dob:
        return ""
    digits = dob.replace("-", "").strip()
    return digits if len(digits) == 8 and digits.isdigit() else ""


def jpeg_to_dicom(
    image_bytes: bytes,
    *,
    patient_name: str = "Anonymous",
    patient_id: str = "",
    date_of_birth: str = "",
    patient_sex: str = "",
    scope: str = "",
    body_part: str = "",
    notes: str = "",
    study_instance_uid: Optional[str] = None,
    series_instance_uid: Optional[str] = None,
    captured_at: Optional[datetime] = None,
) -> bytes:
    """
    Convert a JPEG/PNG image to a DICOM Secondary Capture (.dcm) byte string.

    The image is decoded with Pillow and stored as uncompressed RGB pixel data.
    Passing the same ``study_instance_uid``/``series_instance_uid`` across
    multiple calls groups the resulting instances into one study/series.
    """
    # ── Decode the source image to grayscale ─────────────────────────────
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("L")  # 8-bit single-channel luminance
        width, height = im.size
        pixel_bytes = im.tobytes()

    when = captured_at or datetime.now()
    date_str = when.strftime("%Y%m%d")
    time_str = when.strftime("%H%M%S")

    sop_instance_uid = generate_uid()

    # ── File meta information ────────────────────────────────────────────
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

    ds = Dataset()
    ds.file_meta = file_meta
    # Preamble / DICM marker are written by save_as(enforce_file_format=True)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SpecificCharacterSet = "ISO_IR 100"

    # ── Patient module ───────────────────────────────────────────────────
    ds.PatientName = patient_name or "Anonymous"
    ds.PatientID = patient_id or ""
    ds.PatientBirthDate = _format_birth_date(date_of_birth)
    ds.PatientSex = (patient_sex or "").upper()[:1]

    # ── General Study module ─────────────────────────────────────────────
    ds.StudyInstanceUID = study_instance_uid or generate_uid()
    ds.StudyDate = date_str
    ds.StudyTime = time_str
    ds.StudyID = "1"
    ds.AccessionNumber = ""
    ds.ReferringPhysicianName = ""
    ds.StudyDescription = "IXOPE Medical Examination"

    # ── General Series module ────────────────────────────────────────────
    ds.SeriesInstanceUID = series_instance_uid or generate_uid()
    ds.SeriesNumber = "1"
    ds.Modality = _modality(scope)
    ds.SeriesDescription = f"{(scope or '').upper()} - {body_part or 'General'}".strip()
    body = _body_part(body_part)
    if body:
        ds.BodyPartExamined = body

    # ── General Equipment / SC Equipment modules ─────────────────────────
    ds.Manufacturer = "IXOPE Medical"
    ds.ManufacturerModelName = "IXOPE Device"
    ds.SoftwareVersions = "1.0.0"
    ds.ConversionType = "WSD"  # Workstation

    # ── General Image module ─────────────────────────────────────────────
    ds.InstanceNumber = "1"
    ds.ContentDate = date_str
    ds.ContentTime = time_str
    if notes:
        ds.ImageComments = notes[:10240]

    # ── Image Pixel module (uncompressed grayscale) ─────────────────────
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = height
    ds.Columns = width
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    # Pixel data must be even-length
    if len(pixel_bytes) % 2:
        pixel_bytes += b"\x00"
    ds.PixelData = pixel_bytes

    # ── SOP Common module ────────────────────────────────────────────────
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop_instance_uid

    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()
