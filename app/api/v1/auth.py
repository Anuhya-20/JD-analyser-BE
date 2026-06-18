"""
HR Authentication endpoints.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
    blacklist_token,
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.deps import get_current_hr_user
from app.utils.email import send_otp_email

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


@router.post("/logout", status_code=200)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=True)),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Invalidate the current bearer token.
    The token is added to an in-memory blacklist and rejected on all future requests.
    """
    blacklist_token(credentials.credentials)
    logger.info(f"HR logout: {current_user.email}")
    return {"message": "Logged out successfully"}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate a 6-digit OTP and email it to the user.
    Always returns 200 to avoid leaking whether the email exists.
    """
    result = await db.execute(select(HRUser).where(HRUser.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return ForgotPasswordResponse(
            message="If that email is registered, an OTP has been sent to it."
        )

    otp = "".join(random.choices(string.digits, k=6))
    user.password_reset_token = otp
    user.password_reset_expires = datetime.now(timezone.utc) + timedelta(
        minutes=10
    )
    await db.commit()

    try:
        await send_otp_email(user.email, user.full_name, otp)
    except Exception as e:
        logger.error(f"[Email] Failed to send OTP to {user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP email. Please try again later.",
        )

    logger.info(f"OTP sent to: {user.email}")
    return ForgotPasswordResponse(message="A 6-digit OTP has been sent to your email. It expires in 10 minutes.")


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Reset password using the OTP received via email.
    Requires: email, otp, new_password, confirm_password.
    """
    result = await db.execute(select(HRUser).where(HRUser.email == payload.email))
    user = result.scalar_one_or_none()

    invalid_msg = "Invalid or expired OTP."

    if not user or not user.password_reset_token:
        raise HTTPException(status_code=400, detail=invalid_msg)

    if user.password_reset_expires is None or datetime.now(timezone.utc) > user.password_reset_expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Request a new one.")

    if user.password_reset_token != payload.otp:
        raise HTTPException(status_code=400, detail=invalid_msg)

    user.hashed_password = hash_password(payload.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()

    logger.info(f"Password reset successful for: {user.email}")
    return ResetPasswordResponse(message="Password updated successfully. You can now log in.")
