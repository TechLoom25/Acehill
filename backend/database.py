"""Database engine, session dependency and small additive migrations (no Alembic needed at this size)."""
from collections import defaultdict
from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

# create_all() never alters existing tables, so columns added after v2 are listed here.
_REPAIR_COLUMNS = {
    "service_fee": "INTEGER NOT NULL DEFAULT 0",
    "collected_at": "TIMESTAMP",
    "failure_reason": "VARCHAR NOT NULL DEFAULT ''",
    "failure_by": "VARCHAR NOT NULL DEFAULT ''",
}
# Values added to the Status enum after the first release. PostgreSQL enums are real types and must be extended.
_STATUS_VALUES = ("incomplete",)


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    if "repair" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("repair")}
    with engine.begin() as conn:
        for name, ddl in _REPAIR_COLUMNS.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE repair ADD COLUMN {name} {ddl}"))
            if name == "collected_at":  # back-fill jobs that were collected before we recorded the time
                conn.execute(text("UPDATE repair SET collected_at = updated_at WHERE status = 'collected'"))


def _extend_postgres_status_enum() -> None:
    if engine.dialect.name != "postgresql":
        return
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction on older PostgreSQL versions.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if not conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'status'")).first():
            return
        for value in _STATUS_VALUES:
            conn.execute(text(f"ALTER TYPE status ADD VALUE IF NOT EXISTS '{value}'"))


def normalise_customer_phones() -> None:
    """One-off tidy-up (safe to repeat): store every phone as +254..., merging duplicates created before that rule."""
    from models import Customer, Repair
    from sms import normalise_phone

    with Session(engine) as session:
        groups: dict[str, list[Customer]] = defaultdict(list)
        for customer in session.exec(select(Customer).order_by(Customer.id)):
            try:
                groups[normalise_phone(customer.phone)].append(customer)
            except ValueError:
                continue  # not a recognisable number: leave it alone
        changed = False
        for phone, customers in groups.items():
            keeper, *duplicates = customers
            for dup in duplicates:
                for repair in session.exec(select(Repair).where(Repair.customer_id == dup.id)):
                    repair.customer_id = keeper.id
                session.flush()
                session.delete(dup)
                changed = True
            session.flush()
            if keeper.phone != phone:
                keeper.phone = phone
                changed = True
        if changed:
            session.commit()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    _extend_postgres_status_enum()
    normalise_customer_phones()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
