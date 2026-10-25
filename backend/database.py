"""Database engine, session dependency and a tiny additive migration step."""
from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def _add_missing_repair_columns() -> None:
    """create_all() never alters existing tables, so add columns introduced after v2 by hand."""
    inspector = inspect(engine)
    if "repair" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("repair")}
    with engine.begin() as conn:
        if "service_fee" not in existing:
            conn.execute(text("ALTER TABLE repair ADD COLUMN service_fee INTEGER NOT NULL DEFAULT 0"))
        if "collected_at" not in existing:
            conn.execute(text("ALTER TABLE repair ADD COLUMN collected_at TIMESTAMP"))
            conn.execute(text("UPDATE repair SET collected_at = updated_at WHERE status = 'collected'"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_repair_columns()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
