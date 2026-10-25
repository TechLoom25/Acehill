"""First-run setup, login and self-service account endpoints."""
import hmac
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, func, select

from config import SETUP_KEY
from database import get_session
from models import LoginForm, PasswordChange, Role, SetupForm, TokenOut, User, UserPublic, now_utc
from security import (
    DUMMY_HASH,
    create_access_token,
    current_user,
    hash_password,
    throttle,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_setup_lock = threading.Lock()


def _user_count(session: Session) -> int:
    return session.exec(select(func.count(User.id))).one()


def _token_for(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user), user=UserPublic.model_validate(user))


@router.get("/setup-status")
def setup_status(session: Session = Depends(get_session)):
    """Public: tells the frontend whether to show the first-run admin screen."""
    return {"needs_setup": _user_count(session) == 0, "setup_key_required": bool(SETUP_KEY)}


@router.post("/setup", response_model=TokenOut, status_code=201)
def setup(form: SetupForm, session: Session = Depends(get_session)):
    """Create the first administrator. Only works while there are no users at all."""
    if SETUP_KEY and not hmac.compare_digest(form.setup_key.encode(), SETUP_KEY.encode()):
        raise HTTPException(403, "Invalid setup key.")
    with _setup_lock:
        if _user_count(session) > 0:
            raise HTTPException(409, "Setup has already been completed.")
        user = User(
            username=form.username,
            full_name=form.full_name,
            password_hash=hash_password(form.password),
            role=Role.admin,
            last_login_at=now_utc(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return _token_for(user)


@router.post("/login", response_model=TokenOut)
def login(form: LoginForm, request: Request, session: Session = Depends(get_session)):
    key = f"{request.client.host if request.client else 'unknown'}:{form.username}"
    throttle.check(key)

    user = session.exec(select(User).where(User.username == form.username)).first()
    password_ok = verify_password(form.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok:
        throttle.fail(key)
        raise HTTPException(401, "Incorrect username or password.")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled. Ask an administrator.")

    throttle.reset(key)
    user.last_login_at = now_utc()
    session.add(user)
    session.commit()
    session.refresh(user)
    return _token_for(user)


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(current_user)):
    return user


@router.post("/change-password")
def change_password(
    body: PasswordChange,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    session.add(user)
    session.commit()
    return {"ok": True}
