from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.config import settings


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Token blacklist (in-memory) ───────────────────────────────────────────────
# Stores tokens that have been explicitly logged out before their expiry.
# Automatically purges expired entries to prevent unbounded growth.

_blacklist: dict[str, datetime] = {}  # token → expiry


def blacklist_token(token: str) -> None:
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        exp = datetime.fromtimestamp(data["exp"], tz=timezone.utc)
    except (JWTError, KeyError):
        return
    _blacklist[token] = exp
    _purge_expired_tokens()


def is_token_blacklisted(token: str) -> bool:
    return token in _blacklist


def _purge_expired_tokens() -> None:
    now = datetime.now(timezone.utc)
    expired = [t for t, exp in _blacklist.items() if exp <= now]
    for t in expired:
        del _blacklist[t]


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Return the subject (email) or None if invalid, expired, or blacklisted."""
    if is_token_blacklisted(token):
        return None
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return data.get("sub")
    except JWTError:
        return None


# ── Reset-token helper ────────────────────────────────────────────────────────

def generate_reset_token() -> str:
    """Cryptographically random URL-safe token."""
    return secrets.token_urlsafe(32)


def reset_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.RESET_TOKEN_EXPIRE_HOURS)
