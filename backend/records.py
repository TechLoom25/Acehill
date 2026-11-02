"""Shared clean-up for deleting records, so every delete path removes the same things."""
import logging

from sqlmodel import Session, select

from models import Part, Payment, Repair

audit = logging.getLogger("acehill.audit")  # visible in: journalctl -u acehill-backend


def purge_repair(session: Session, repair: Repair) -> tuple[int, int, int]:
    """Delete a repair with its parts and payments (caller commits). Returns (parts, payments, KES received)."""
    parts = session.exec(select(Part).where(Part.repair_id == repair.id)).all()
    payments = session.exec(select(Payment).where(Payment.repair_id == repair.id)).all()
    received = sum(p.amount for p in payments)
    for row in (*parts, *payments):
        session.delete(row)
    session.delete(repair)
    return len(parts), len(payments), received
