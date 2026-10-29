"""Customer experience points and tiers, derived from history so they can never drift out of sync.

A *visit* is a repair that was collected and was not marked "could not complete".
    points = POINTS_PER_VISIT per visit  +  1 per SPEND_PER_POINT KES billed on those visits
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, func, select

from models import Part, Repair, Status

POINTS_PER_VISIT = 10
SPEND_PER_POINT = 100  # KES
TIERS = ((600, "Platinum"), (300, "Gold"), (100, "Silver"), (10, "Returning"), (0, "New"))


def tier_for(points: int) -> str:
    return next(name for floor, name in TIERS if points >= floor)


@dataclass
class CustomerStats:
    repairs: int = 0
    visits: int = 0
    spent: int = 0
    last_visit: Optional[datetime] = None

    @property
    def points(self) -> int:
        return self.visits * POINTS_PER_VISIT + self.spent // SPEND_PER_POINT

    @property
    def tier(self) -> str:
        return tier_for(self.points)


def customer_stats(session: Session, customer_ids: list[int]) -> dict[int, CustomerStats]:
    """Stats for many customers using two queries, whatever the number of customers."""
    stats = {cid: CustomerStats() for cid in customer_ids}
    if not stats:
        return stats

    counted: dict[int, int] = {}  # repair id -> customer id, for visits that earn points
    rows = session.exec(
        select(Repair.id, Repair.customer_id, Repair.status, Repair.failure_reason, Repair.service_fee, Repair.created_at)
        .where(col(Repair.customer_id).in_(list(stats)))
    ).all()
    for repair_id, customer_id, status, reason, fee, created_at in rows:
        s = stats[customer_id]
        s.repairs += 1
        if s.last_visit is None or created_at > s.last_visit:
            s.last_visit = created_at
        if status == Status.collected and not reason:
            s.visits += 1
            s.spent += fee
            counted[repair_id] = customer_id

    if counted:
        for repair_id, total in session.exec(
            select(Part.repair_id, func.sum(Part.unit_price * Part.quantity))
            .where(col(Part.repair_id).in_(list(counted)))
            .group_by(Part.repair_id)
        ):
            stats[counted[repair_id]].spent += int(total)
    return stats
