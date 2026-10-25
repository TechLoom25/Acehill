"""Money calculations and per-role visibility, shared by the repair, billing and report routes."""
from collections import defaultdict
from collections.abc import Iterable
from typing import Optional

from sqlmodel import Session, col, func, select

from models import MoneyOut, Part, PartOut, Payment, PaymentOut, Repair, RepairOut, Role, User


def has_finance_access(user: User) -> bool:
    """Prices, costs and payments are hidden from technicians."""
    return user.role in (Role.admin, Role.manager, Role.front_desk)


def compute_money(repair: Repair, parts: Iterable[Part], paid: int, *, include_profit: bool) -> MoneyOut:
    parts = list(parts)
    parts_total = sum(p.unit_price * p.quantity for p in parts)
    parts_cost = sum(p.unit_cost * p.quantity for p in parts)
    total = repair.service_fee + parts_total
    return MoneyOut(
        service_fee=repair.service_fee,
        parts_total=parts_total,
        parts_cost=parts_cost,
        total=total,
        paid=paid,
        balance=total - paid,
        profit=total - parts_cost if include_profit else None,
    )


def part_out(part: Part, user: User) -> PartOut:
    data = part.model_dump()
    if not has_finance_access(user):
        data["unit_cost"] = data["unit_price"] = None
    return PartOut(**data)


def payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut(**payment.model_dump())


def build_repair_outs(
    session: Session,
    user: User,
    rows: list[tuple[Repair, str]],
    sms_sent: Optional[bool] = None,
) -> list[RepairOut]:
    """Turn (repair, customer name) rows into API objects with money figures, using two queries in total."""
    if not rows:
        return []
    parts_by: dict[int, list[Part]] = defaultdict(list)
    paid_by: dict[int, int] = defaultdict(int)
    show_money = has_finance_access(user)
    if show_money:
        ids = [repair.id for repair, _ in rows]
        for part in session.exec(select(Part).where(col(Part.repair_id).in_(ids))):
            parts_by[part.repair_id].append(part)
        for repair_id, total in session.exec(
            select(Payment.repair_id, func.sum(Payment.amount))
            .where(col(Payment.repair_id).in_(ids))
            .group_by(Payment.repair_id)
        ):
            paid_by[repair_id] = int(total)

    outs = []
    for repair, customer_name in rows:
        money = (
            compute_money(repair, parts_by[repair.id], paid_by[repair.id], include_profit=user.role == Role.admin)
            if show_money
            else None
        )
        outs.append(RepairOut(**repair.model_dump(), customer_name=customer_name, money=money, sms_sent=sms_sent))
    return outs
