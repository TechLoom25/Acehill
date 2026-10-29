"""Customer directory with loyalty points, and the phone lookup used when registering a repair."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, or_, select

from database import get_session
from loyalty import customer_stats
from models import Customer, CustomerLookup, CustomerOut, Role, User
from security import require_roles
from sms import normalise_phone

router = APIRouter(tags=["customers"])
can_view_customers = require_roles(Role.manager, Role.front_desk)


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(
    q: Optional[str] = Query(None, max_length=80, description="Search name or phone"),
    session: Session = Depends(get_session),
    _: User = Depends(can_view_customers),
):
    stmt = select(Customer).order_by(Customer.name)
    if q and q.strip():
        term = q.strip()
        stmt = stmt.where(
            or_(col(Customer.name).icontains(term, autoescape=True), col(Customer.phone).icontains(term, autoescape=True))
        )
    customers = session.exec(stmt).all()
    stats = customer_stats(session, [c.id for c in customers])
    return [
        CustomerOut(
            id=c.id,
            name=c.name,
            phone=c.phone,
            created_at=c.created_at,
            repairs=stats[c.id].repairs,
            visits=stats[c.id].visits,
            points=stats[c.id].points,
            tier=stats[c.id].tier,
            total_spent=stats[c.id].spent,
            last_visit=stats[c.id].last_visit,
        )
        for c in customers
    ]


@router.get("/customers/lookup", response_model=CustomerLookup)
def lookup_customer(
    phone: str = Query(..., max_length=30),
    session: Session = Depends(get_session),
    _: User = Depends(can_view_customers),
):
    """Used by the registration form: type a number, get the saved name and loyalty tier."""
    try:
        normalised = normalise_phone(phone)
    except ValueError:
        return CustomerLookup(found=False)
    customer = session.exec(select(Customer).where(Customer.phone == normalised)).first()
    if customer is None:
        return CustomerLookup(found=False)
    s = customer_stats(session, [customer.id])[customer.id]
    return CustomerLookup(found=True, name=customer.name, visits=s.visits, points=s.points, tier=s.tier)
