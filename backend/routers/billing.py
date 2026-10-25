"""Parts needed for a repair, and customer payments."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from database import get_session
from finance import has_finance_access, part_out, payment_out
from models import (
    Part,
    PartCreate,
    PartOut,
    PartSource,
    PartUpdate,
    Payment,
    PaymentCreate,
    PaymentOut,
    Repair,
    Role,
    Status,
    User,
)
from security import current_user, require_roles

router = APIRouter(tags=["billing"])
can_take_payments = require_roles(Role.manager, Role.front_desk)
admin_only = require_roles()

_PRICE_FIELDS = ("unit_cost", "unit_price")


def _open_repair(session: Session, repair_id: int, user: User) -> Repair:
    """Fetch a repair whose parts may still be changed (collected jobs are locked for non-admins)."""
    repair = session.get(Repair, repair_id)
    if repair is None:
        raise HTTPException(404, "Repair not found.")
    if repair.status == Status.collected and user.role != Role.admin:
        raise HTTPException(409, "This repair has been collected. Ask an administrator to change its parts.")
    return repair


def _require_finance(user: User) -> None:
    if not has_finance_access(user):
        raise HTTPException(403, "Only front desk, managers and admins can enter prices.")


# ---------- parts ----------
@router.post("/repairs/{repair_id}/parts", response_model=PartOut, status_code=201)
def add_part(
    repair_id: int,
    body: PartCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Any staff member can list a part. Only finance roles can put prices on it."""
    _open_repair(session, repair_id, user)
    if body.unit_cost is not None or body.unit_price is not None:
        _require_finance(user)
    cost = body.unit_cost or 0
    part = Part(
        repair_id=repair_id,
        name=body.name,
        quantity=body.quantity,
        source=body.source,
        unit_cost=cost,
        unit_price=body.unit_price if body.unit_price is not None else cost,
        acquired=body.acquired if body.acquired is not None else body.source == PartSource.stock,
        added_by=user.full_name,
    )
    session.add(part)
    session.commit()
    session.refresh(part)
    return part_out(part, user)


@router.patch("/parts/{part_id}", response_model=PartOut)
def update_part(
    part_id: int,
    body: PartUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found.")
    _open_repair(session, part.repair_id, user)

    changes = body.model_dump(exclude_unset=True)
    changes = {k: v for k, v in changes.items() if v is not None}
    if any(k in changes for k in _PRICE_FIELDS):
        _require_finance(user)
    # A part sold at cost (no markup) keeps its price in step when only the cost is edited.
    if "unit_cost" in changes and "unit_price" not in changes and part.unit_price == part.unit_cost:
        changes["unit_price"] = changes["unit_cost"]
    for key, value in changes.items():
        setattr(part, key, value)
    session.add(part)
    session.commit()
    session.refresh(part)
    return part_out(part, user)


@router.delete("/parts/{part_id}")
def delete_part(part_id: int, session: Session = Depends(get_session), user: User = Depends(current_user)):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found.")
    _open_repair(session, part.repair_id, user)
    session.delete(part)
    session.commit()
    return {"ok": True}


# ---------- payments ----------
@router.post("/repairs/{repair_id}/payments", response_model=PaymentOut, status_code=201)
def add_payment(
    repair_id: int,
    body: PaymentCreate,
    session: Session = Depends(get_session),
    user: User = Depends(can_take_payments),
):
    if session.get(Repair, repair_id) is None:
        raise HTTPException(404, "Repair not found.")
    payment = Payment(
        repair_id=repair_id,
        amount=body.amount,
        method=body.method,
        reference=body.reference.strip(),
        received_by=user.full_name,
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment_out(payment)


@router.delete("/payments/{payment_id}")
def delete_payment(payment_id: int, session: Session = Depends(get_session), _: User = Depends(admin_only)):
    """Administrators only, to correct a mistake. Payments are otherwise a permanent record."""
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found.")
    session.delete(payment)
    session.commit()
    return {"ok": True}
