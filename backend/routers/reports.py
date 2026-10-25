"""Administrator finance reports."""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, func, select

from config import SHOP_TIMEZONE
from database import get_session
from models import Part, Payment, Repair, Status, User, now_utc
from security import require_roles

router = APIRouter(prefix="/reports", tags=["reports"])
admin_only = require_roles()

Period = Literal["today", "week", "last_week", "month", "last_month"]


def period_bounds(period: str, now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return [start, end) as timezone-aware UTC datetimes. Weeks run Monday to Sunday in shop time."""
    today = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)
    if period == "today":
        start, end = today, today + timedelta(days=1)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    elif period == "last_week":
        end = today - timedelta(days=today.weekday())
        start = end - timedelta(days=7)
    else:
        first = today.replace(day=1)
        if period == "month":
            start, end = first, (first + timedelta(days=32)).replace(day=1)
        else:  # last_month
            end = first
            start = (first - timedelta(days=1)).replace(day=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


@router.get("/finance")
def finance_report(
    period: Period = "week",
    session: Session = Depends(get_session),
    _: User = Depends(admin_only),
):
    """
    Two honest views of the money:
      * cash received  - payments taken in the period, whatever job they belong to
      * profit         - jobs *collected* in the period: (service fee + parts charged) - parts cost
    """
    tz = ZoneInfo(SHOP_TIMEZONE)
    start, end = period_bounds(period, now_utc(), tz)

    # ----- cash received -----
    payments = session.exec(select(Payment).where(Payment.created_at >= start, Payment.created_at < end)).all()
    by_method: dict[str, int] = defaultdict(int)
    cash_by_day: dict[str, int] = defaultdict(int)
    for p in payments:
        by_method[p.method.value] += p.amount
        cash_by_day[p.created_at.astimezone(tz).date().isoformat()] += p.amount

    # ----- jobs collected in the period -----
    collected = session.exec(
        select(Repair).where(col(Repair.collected_at) >= start, col(Repair.collected_at) < end)
    ).all()
    parts_by_repair: dict[int, list[Part]] = defaultdict(list)
    if collected:
        ids = [r.id for r in collected]
        for part in session.exec(select(Part).where(col(Part.repair_id).in_(ids))):
            parts_by_repair[part.repair_id].append(part)

    service_income = parts_revenue = parts_cost = parts_without_cost = 0
    profit_by_day: dict[str, int] = defaultdict(int)
    for r in collected:
        parts = parts_by_repair[r.id]
        revenue_parts = sum(p.unit_price * p.quantity for p in parts)
        cost = sum(p.unit_cost * p.quantity for p in parts)
        service_income += r.service_fee
        parts_revenue += revenue_parts
        parts_cost += cost
        parts_without_cost += sum(1 for p in parts if p.unit_cost == 0)
        profit_by_day[r.collected_at.astimezone(tz).date().isoformat()] += r.service_fee + revenue_parts - cost

    revenue = service_income + parts_revenue

    # ----- money still owed, across every repair -----
    fees = dict(session.exec(select(Repair.id, Repair.service_fee)).all())
    parts_charged = dict(
        session.exec(select(Part.repair_id, func.sum(Part.unit_price * Part.quantity)).group_by(Part.repair_id)).all()
    )
    paid = dict(session.exec(select(Payment.repair_id, func.sum(Payment.amount)).group_by(Payment.repair_id)).all())
    owed = [
        fees[rid] + int(parts_charged.get(rid, 0)) - int(paid.get(rid, 0))
        for rid in fees
    ]
    outstanding = [o for o in owed if o > 0]

    # ----- one row per local day -----
    local_start = start.astimezone(tz).date()
    local_end = end.astimezone(tz).date()
    days = [local_start + timedelta(days=i) for i in range((local_end - local_start).days)]
    daily = [
        {"date": d.isoformat(), "cash": cash_by_day.get(d.isoformat(), 0), "profit": profit_by_day.get(d.isoformat(), 0)}
        for d in days
    ]

    return {
        "period": period,
        "start": local_start.isoformat(),
        "end": (local_end - timedelta(days=1)).isoformat(),
        "cash_received": sum(p.amount for p in payments),
        "payments_count": len(payments),
        "by_method": dict(by_method),
        "repairs_collected": len(collected),
        "revenue": revenue,
        "service_income": service_income,
        "parts_revenue": parts_revenue,
        "parts_cost": parts_cost,
        "profit": revenue - parts_cost,
        "parts_without_cost": parts_without_cost,
        "outstanding": sum(outstanding),
        "outstanding_count": len(outstanding),
        "daily": daily,
    }
