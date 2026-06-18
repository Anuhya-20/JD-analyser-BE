"""
HR Authentication endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.database import get_db
from app.models.hr_user import HRUser
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    HRUserCreate,
    HRUserResponse,
    LoginRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
)
from app.core.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    reset_token_expiry,
    verify_password,
)
from app.core.deps import get_current_hr_user

router = APIRouter()


@router.post("/register", response_model=HRUserResponse, status_code=201)
async def register_hr_user(payload: HRUserCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new HR user account.
    (In production: restrict this to super-admin only.)
    """
    existing = await db.execute(select(HRUser).where(HRUser.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = HRUser(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"Registered new HR user: {user.email}")
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    HR Login — returns a JWT bearer token on success.
    """
    result = await db.execute(select(HRUser).where(HRUser.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact the administrator.",
        )

    token = create_access_token(subject=user.email)
    logger.info(f"HR login: {user.email}")
    return TokenResponse(access_token=token, hr_user=HRUserResponse.model_validate(user))


@router.get("/me", response_model=HRUserResponse)
async def get_me(current_user: HRUser = Depends(get_current_hr_user)):
    """Return the currently authenticated HR user's profile."""
    return current_user


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Request a password reset token.
    In production the token is emailed; here it is returned in the response for testing.
    """
    result = await db.execute(select(HRUser).where(HRUser.email == payload.email))
    user = result.scalar_one_or_none()

    # Always return 200 so we don't leak whether the email exists
    if not user or not user.is_active:
        return ForgotPasswordResponse(
            message="If that email is registered you will receive a reset link shortly."
        )

    token = generate_reset_token()
    user.password_reset_token = token
    user.password_reset_expires = reset_token_expiry()
    await db.commit()

    logger.info(f"Password reset requested for: {user.email}")

    return ForgotPasswordResponse(
        message="Password reset token generated. Use it within 1 hour.",
        reset_token=token,   # In production: send via email, omit from response
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Reset password using the token received from /forgot-password.
    Requires: reset_token, new_password, confirm_password.
    """
    result = await db.execute(
        select(HRUser).where(HRUser.password_reset_token == payload.reset_token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if user.password_reset_expires is None or datetime.now(timezone.utc) > user.password_reset_expires:
        raise HTTPException(status_code=400, detail="Reset token has expired. Request a new one.")

    user.hashed_password = hash_password(payload.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()

    logger.info(f"Password reset successful for: {user.email}")
    return ResetPasswordResponse(message="Password updated successfully. You can now log in.")
