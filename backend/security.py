"""Password hashing, access tokens, login throttling and role checks."""
import base64
import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from config import SECRET_KEY, TOKEN_TTL_MINUTES
from database import get_session
from models import Role, User, now_utc

# ---------- passwords (scrypt from the standard library) ----------
_N, _R, _P = 2**14, 8, 1


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


# Verified against when the username is unknown, so response time doesn't reveal valid usernames.
DUMMY_HASH = hash_password("not-a-real-password")


# ---------- tokens ----------
def create_access_token(user: User) -> str:
    now = now_utc()
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _user_id_from_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


# ---------- login throttle (in-memory; resets on restart) ----------
class LoginThrottle:
    def __init__(self, max_failures: int = 5, window_seconds: int = 900) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]
        return self._failures[key]

    def check(self, key: str) -> None:
        with self._lock:
            if len(self._recent(key)) >= self.max_failures:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many failed attempts. Please wait a few minutes and try again.",
                )

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)


throttle = LoginThrottle()

# ---------- request dependencies ----------
_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the signed-in user. Re-reads the DB so disabling an account takes effect immediately."""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Please sign in again.", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    user_id = _user_id_from_token(creds.credentials)
    user = session.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*roles: Role):
    """Allow the given roles (admins always pass)."""
    allowed = {Role.admin, *roles}

    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to do that.")
        return user

    return dependency
