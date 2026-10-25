"""Repairs, customers, SMS, public tracking and the dashboard."""
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, or_, select

from database import get_session
from finance import build_repair_outs, has_finance_access, part_out, payment_out
from models import (
    OPEN_STATUSES,
    BulkSMS,
    Customer,
    IntakeForm,
    Part,
    PartSource,
    Payment,
    Repair,
    RepairDetail,
    RepairOut,
    RepairUpdate,
    Role,
    Status,
    User,
    now_utc,
)
from security import current_user, require_roles
from sms import send_sms, try_send_sms

router = APIRouter(tags=["shop"])

can_intake = require_roles(Role.manager, Role.front_desk)
can_view_customers = require_roles(Role.manager, Role.front_desk)
can_bulk_sms = require_roles(Role.manager)

STATUS_MESSAGES = {
    Status.diagnosing: "is being diagnosed",
    Status.waiting_parts: "is waiting for parts",
    Status.repairing: "is now being repaired",
    Status.ready: "is READY for pickup",
    Status.collected: "has been collected. Thank you!",
}


# ---------- repairs ----------
@router.post("/repairs", response_model=RepairOut, status_code=201)
def register_repair(form: IntakeForm, session: Session = Depends(get_session), user: User = Depends(can_intake)):
    customer = session.exec(select(Customer).where(Customer.phone == form.phone)).first()
    if customer is None:
        customer = Customer(name=form.name, phone=form.phone)
        session.add(customer)
        session.commit()
        session.refresh(customer)

    repair = None
    for _attempt in range(5):  # ticket codes are short, so retry on the rare collision
        candidate = Repair(
            ticket_code=secrets.token_hex(3).upper(),
            customer_id=customer.id,
            **form.model_dump(exclude={"name", "phone", "deposit_amount", "deposit_method"}),
        )
        session.add(candidate)
        try:
            session.commit()
            repair = candidate
            break
        except IntegrityError:
            session.rollback()
    if repair is None:
        raise HTTPException(500, "Could not allocate a ticket code. Please try again.")
    session.refresh(repair)

    if form.deposit_amount > 0:
        session.add(
            Payment(
                repair_id=repair.id,
                amount=form.deposit_amount,
                method=form.deposit_method,
                reference="Deposit at intake",
                received_by=user.full_name,
            )
        )
        session.commit()

    sent = try_send_sms(
        [customer.phone],
        f"Hi {customer.name}, Acehill Repair has received your {repair.brand} "
        f"{repair.model}. Ticket: {repair.ticket_code}.",
    )
    return build_repair_outs(session, user, [(repair, customer.name)], sms_sent=sent)[0]


@router.get("/repairs", response_model=list[RepairOut])
def list_repairs(
    status: Optional[Status] = None,
    q: Optional[str] = Query(None, max_length=80, description="Search ticket, IMEI, device or customer"),
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    stmt = (
        select(Repair, Customer.name)
        .join(Customer, Customer.id == Repair.customer_id)
        .order_by(col(Repair.created_at).desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Repair.status == status)
    if q and q.strip():
        term = q.strip()
        stmt = stmt.where(
            or_(
                col(Repair.ticket_code).icontains(term, autoescape=True),
                col(Repair.imei).icontains(term, autoescape=True),
                col(Repair.brand).icontains(term, autoescape=True),
                col(Repair.model).icontains(term, autoescape=True),
                col(Customer.name).icontains(term, autoescape=True),
            )
        )
    return build_repair_outs(session, user, [(r, name) for r, name in session.exec(stmt).all()])


@router.get("/repairs/{repair_id}", response_model=RepairDetail)
def repair_detail(repair_id: int, session: Session = Depends(get_session), user: User = Depends(current_user)):
    repair = session.get(Repair, repair_id)
    if repair is None:
        raise HTTPException(404, "Repair not found.")
    customer = session.get(Customer, repair.customer_id)
    base = build_repair_outs(session, user, [(repair, customer.name)])[0]
    parts = session.exec(select(Part).where(Part.repair_id == repair.id).order_by(col(Part.created_at))).all()
    payments = (
        session.exec(select(Payment).where(Payment.repair_id == repair.id).order_by(col(Payment.created_at))).all()
        if has_finance_access(user)
        else []
    )
    return RepairDetail(
        **base.model_dump(),
        parts=[part_out(p, user) for p in parts],
        payments=[payment_out(p) for p in payments],
    )


@router.patch("/repairs/{repair_id}", response_model=RepairOut)
def update_repair(
    repair_id: int,
    upd: RepairUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    repair = session.get(Repair, repair_id)
    if repair is None:
        raise HTTPException(404, "Repair not found.")

    data = upd.model_dump(exclude_unset=True, exclude={"notify"})
    for key in ("status", "progress", "assigned_to", "service_fee"):  # these columns are not nullable
        if key in data and data[key] is None:
            del data[key]
    if "service_fee" in data:
        if not has_finance_access(user):
            raise HTTPException(403, "Only front desk, managers and admins can change the service fee.")
        if repair.status == Status.collected and user.role != Role.admin:
            raise HTTPException(409, "This repair has been collected. Ask an administrator to change its price.")
    eta = data.get("estimated_completion")
    if eta is not None and eta.tzinfo is None:
        data["estimated_completion"] = eta.replace(tzinfo=now_utc().tzinfo)

    old_status = repair.status
    for key, value in data.items():
        setattr(repair, key, value)
    if repair.status != old_status:
        if repair.status == Status.collected:
            repair.collected_at = now_utc()
        elif old_status == Status.collected:
            repair.collected_at = None
    repair.updated_at = now_utc()
    session.add(repair)
    session.commit()
    session.refresh(repair)

    customer = session.get(Customer, repair.customer_id)
    sent = None
    if upd.notify and repair.status != old_status and repair.status in STATUS_MESSAGES:
        sent = try_send_sms(
            [customer.phone],
            f"Acehill Repair: your {repair.brand} {repair.model} "
            f"{STATUS_MESSAGES[repair.status]}. Ticket {repair.ticket_code}.",
        )
    return build_repair_outs(session, user, [(repair, customer.name)], sms_sent=sent)[0]


# ---------- public tracking ----------
@router.get("/track/{ticket_code}")
def track(ticket_code: str, session: Session = Depends(get_session)):
    """Public: customer checks progress. Returns no personal or financial data."""
    r = session.exec(select(Repair).where(Repair.ticket_code == ticket_code.strip().upper())).first()
    if r is None:
        raise HTTPException(404, "Ticket not found.")
    return {
        "ticket_code": r.ticket_code,
        "device": f"{r.brand} {r.model}",
        "status": r.status,
        "progress": r.progress,
        "estimated_completion": r.estimated_completion,
        "updated_at": r.updated_at,
    }


# ---------- customers & SMS ----------
@router.get("/customers")
def list_customers(session: Session = Depends(get_session), _: User = Depends(can_view_customers)):
    return session.exec(select(Customer).order_by(Customer.name)).all()


@router.post("/sms/bulk")
def bulk_sms(body: BulkSMS, session: Session = Depends(get_session), _: User = Depends(can_bulk_sms)):
    known = [c.phone for c in session.exec(select(Customer)).all()]
    if body.phones is None:
        phones = known
    else:  # only ever message numbers that belong to a registered customer
        wanted = set(body.phones)
        phones = [p for p in known if p in wanted]
    if not phones:
        raise HTTPException(400, "No recipients.")
    try:
        accepted = send_sms(phones, body.message)
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "The SMS provider rejected the request. Nothing was confirmed as sent.")
    return {"sent_to": accepted, "failed": len(phones) - accepted}


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session), user: User = Depends(current_user)):
    now = now_utc()
    week_ago = now - timedelta(days=7)

    by_status = {s.value: 0 for s in Status}
    for status_, count in session.exec(select(Repair.status, func.count(Repair.id)).group_by(Repair.status)).all():
        by_status[status_.value] = count

    open_filter = col(Repair.status).in_(OPEN_STATUSES)
    overdue = session.exec(
        select(func.count(Repair.id)).where(open_filter, col(Repair.estimated_completion) < now)
    ).one()
    new_week = session.exec(select(func.count(Repair.id)).where(Repair.created_at >= week_ago)).one()
    done_week = session.exec(
        select(func.count(Repair.id)).where(
            col(Repair.status).in_((Status.ready, Status.collected)), Repair.updated_at >= week_ago
        )
    ).one()
    customers = session.exec(select(func.count(Customer.id))).one()

    workload = [
        {"name": name or "Unassigned", "open": count}
        for name, count in session.exec(
            select(Repair.assigned_to, func.count(Repair.id))
            .where(open_filter)
            .group_by(Repair.assigned_to)
            .order_by(func.count(Repair.id).desc())
        ).all()
    ]

    rows = session.exec(
        select(Repair, Customer.name)
        .join(Customer, Customer.id == Repair.customer_id)
        .order_by(col(Repair.created_at).desc())
        .limit(6)
    ).all()
    recent = build_repair_outs(session, user, [(r, name) for r, name in rows])

    to_buy = session.exec(
        select(Part, Repair.ticket_code, Repair.brand, Repair.model)
        .join(Repair, Repair.id == Part.repair_id)
        .where(Part.source == PartSource.purchase, Part.acquired == False, Repair.status != Status.collected)  # noqa: E712
        .order_by(col(Part.created_at))
    ).all()
    parts_to_buy = [
        {"id": p.id, "repair_id": p.repair_id, "name": p.name, "quantity": p.quantity, "ticket_code": code, "device": f"{brand} {model}"}
        for p, code, brand, model in to_buy[:8]
    ]

    return {
        "open": sum(by_status[s.value] for s in OPEN_STATUSES),
        "ready": by_status[Status.ready.value],
        "overdue": overdue,
        "new_this_week": new_week,
        "completed_this_week": done_week,
        "customers": customers,
        "by_status": by_status,
        "workload": workload,
        "recent": recent,
        "parts_to_buy": parts_to_buy,
        "parts_to_buy_count": len(to_buy),
    }
