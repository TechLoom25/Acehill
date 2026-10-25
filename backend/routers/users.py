"""Staff account management (administrators only) and the staff directory."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database import get_session
from models import Role, StaffMember, User, UserCreate, UserPublic, UserUpdate
from security import current_user, hash_password, require_roles

router = APIRouter(tags=["staff"])
admin_only = require_roles()  # admins always pass; nobody else is listed


@router.get("/staff", response_model=list[StaffMember])
def staff_directory(session: Session = Depends(get_session), _: User = Depends(current_user)):
    """Active staff, for technician pickers. Available to every signed-in user."""
    return session.exec(select(User).where(User.is_active == True).order_by(User.full_name)).all()  # noqa: E712


@router.get("/users", response_model=list[UserPublic])
def list_users(session: Session = Depends(get_session), _: User = Depends(admin_only)):
    return session.exec(select(User).order_by(User.full_name)).all()


@router.post("/users", response_model=UserPublic, status_code=201)
def create_user(body: UserCreate, session: Session = Depends(get_session), _: User = Depends(admin_only)):
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "That username is already taken.")
    session.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int,
    body: UserUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(admin_only),
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")

    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        changes.get("role", user.role) != Role.admin or changes.get("is_active", user.is_active) is False
    ):
        # Prevents locking the organisation out of its own admin console.
        raise HTTPException(400, "You can't remove your own admin access or disable your own account.")

    password = changes.pop("password", None)
    for field in ("full_name", "role", "is_active"):
        if changes.get(field) is not None:
            setattr(user, field, changes[field])
    if password:
        user.password_hash = hash_password(password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
