"""
Auth routes — Register, Login, Get current user.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.core.database import get_db
from app.core.auth import hash_password, verify_password, create_access_token, get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: Optional[str] = ""
    role: Optional[str] = "doctor"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if email or username exists
    existing = await db.execute(
        select(User).where((User.email == data.email) | (User.username == data.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email or username already exists")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username/email and password. Returns JWT token."""
    # Find user by username or email
    result = await db.execute(
        select(User).where((User.username == data.username) | (User.email == data.username))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    if not user.is_active:
        raise HTTPException(403, "Account is disabled")

    # Create JWT token
    token = create_access_token(data={"sub": user.id, "role": user.role})

    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        },
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user


# ─── Create sample user on first run ─────────────────────────────────────────
@router.post("/seed", include_in_schema=False)
async def seed_sample_user(db: AsyncSession = Depends(get_db)):
    """Create sample login user (run once)."""
    existing = await db.execute(select(User).where(User.email == "ixope@ixope-hub.com"))
    if existing.scalar_one_or_none():
        return {"message": "Sample user already exists"}

    user = User(
        email="ixope@ixope-hub.com",
        username="ixope",
        hashed_password=hash_password("ixope@123"),
        full_name="Dr. Demo",
        role="doctor",
    )
    db.add(user)

    admin = User(
        email="admin@ixope-hub.com",
        username="admin",
        hashed_password=hash_password("ixope@321"),
        full_name="Admin",
        role="admin",
    )
    db.add(admin)

    await db.commit()
    return {"message": "Sample users created: ixope@ixope-hub.com / ixope@123, admin@ixope-hub.com / ixope@321"}
