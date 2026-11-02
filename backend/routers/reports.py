"""Administrator finance reports."""
from collections import defaultdict
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, func, select

from database import get_session
from models import Customer, Part, Payment, Repair, User, now_utc
from security import require_roles
from timeutil import as_utc, period_bounds, shop_tz

router = APIRouter(prefix="/reports", tags=["reports"])
admin_only = require_roles()

Period = Literal["today", "week", "last_week", "month", "last_month"]

__all__ = ["router", "period_bounds"]  # period_bounds is re-exported for tests and callers that imported it from here


@router.get("/finance")
def finance_report(
    period: Period = "week",
    session: Session = Depends(get_session),
    _: User = Depends(admin_only),
):
    """
    Two honest views of the money:
      * cash received - payments taken in the period, whatever job they belong to
      * service / parts / profit - jobs *collected* in the period:
            service charged = service fees;  parts cost = what the shop paid;  parts charged = what customers paid for parts
            profit = service charged + parts charged - parts cost
    """
    tz = shop_tz()
    start, end = period_bounds(period, now_utc(), tz)

    def local_day(value) -> str:
        return as_utc(value).astimezone(tz).date().isoformat()

    # ----- cash received -----
    payments = session.exec(select(Payment).where(Payment.created_at >= start, Payment.created_at < end)).all()
    by_method: dict[str, int] = defaultdict(int)
    daily: dict[str, dict] = defaultdict(
        lambda: {"cash": 0, "jobs": 0, "service": 0, "parts_cost": 0, "parts_charged": 0, "profit": 0}
    )
    for p in payments:
        by_method[p.method.value] += p.amount
        daily[local_day(p.created_at)]["cash"] += p.amount

    # ----- jobs collected in the period -----
    rows = session.exec(
        select(Repair, Customer)
        .join(Customer, Customer.id == Repair.customer_id)
        .where(col(Repair.collected_at) >= start, col(Repair.collected_at) < end)
        .order_by(col(Repair.collected_at))
    ).all()
    parts_by_repair: dict[int, list[Part]] = defaultdict(list)
    if rows:
        ids = [r.id for r, _ in rows]
        for part in session.exec(select(Part).where(col(Part.repair_id).in_(ids))):
            parts_by_repair[part.repair_id].append(part)

    service_income = parts_revenue = parts_cost = parts_without_cost = jobs_with_parts = 0
    jobs = []
    for r, customer in rows:
        parts = parts_by_repair[r.id]
        charged = sum(p.unit_price * p.quantity for p in parts)
        cost = sum(p.unit_cost * p.quantity for p in parts)
        profit = r.service_fee + charged - cost
        service_income += r.service_fee
        parts_revenue += charged
        parts_cost += cost
        parts_without_cost += sum(1 for p in parts if p.unit_cost == 0)
        jobs_with_parts += 1 if parts else 0

        day = daily[local_day(r.collected_at)]
        day["jobs"] += 1
        day["service"] += r.service_fee
        day["parts_cost"] += cost
        day["parts_charged"] += charged
        day["profit"] += profit
        jobs.append(
            {
                "repair_id": r.id,
                "ticket_code": r.ticket_code,
                "device": f"{r.brand} {r.model}",
                "customer": customer.name,
                "collected_at": r.collected_at,
                "service": r.service_fee,
                "parts_cost": cost,
                "parts_charged": charged,
                "total": r.service_fee + charged,
                "profit": profit,
                "had_parts": bool(parts),
                "incomplete": bool(r.failure_reason),
            }
        )

    revenue = service_income + parts_revenue

    # ----- money still owed, across every repair -----
    fees = dict(session.exec(select(Repair.id, Repair.service_fee)).all())
    parts_charged_by = dict(
        session.exec(select(Part.repair_id, func.sum(Part.unit_price * Part.quantity)).group_by(Part.repair_id)).all()
    )
    paid = dict(session.exec(select(Payment.repair_id, func.sum(Payment.amount)).group_by(Payment.repair_id)).all())
    owed = [fees[rid] + int(parts_charged_by.get(rid, 0)) - int(paid.get(rid, 0)) for rid in fees]
    outstanding = [o for o in owed if o > 0]

    # ----- one row per local day, including quiet ones -----
    local_start = start.astimezone(tz).date()
    local_end = end.astimezone(tz).date()
    empty = {"cash": 0, "jobs": 0, "service": 0, "parts_cost": 0, "parts_charged": 0, "profit": 0}
    days = [local_start + timedelta(days=i) for i in range((local_end - local_start).days)]
    daily_rows = [{"date": d.isoformat(), **daily.get(d.isoformat(), empty)} for d in days]

    return {
        "period": period,
        "start": local_start.isoformat(),
        "end": (local_end - timedelta(days=1)).isoformat(),
        "cash_received": sum(p.amount for p in payments),
        "payments_count": len(payments),
        "by_method": dict(by_method),
        "repairs_collected": len(rows),
        "service_only_jobs": len(rows) - jobs_with_parts,
        "jobs_with_parts": jobs_with_parts,
        "revenue": revenue,
        "service_income": service_income,
        "parts_revenue": parts_revenue,
        "parts_cost": parts_cost,
        "profit": revenue - parts_cost,
        "parts_without_cost": parts_without_cost,
        "outstanding": sum(outstanding),
        "outstanding_count": len(outstanding),
        "daily": daily_rows,
        "jobs": jobs,
    }
