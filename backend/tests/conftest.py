import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-0123456789")
os.environ["AT_API_KEY"] = ""
os.environ["SETUP_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

import sms  # noqa: E402
from database import get_session  # noqa: E402
from main import app  # noqa: E402
from security import throttle  # noqa: E402


@pytest.fixture()
def client():
    url = os.getenv("TEST_DATABASE_URL")  # e.g. a throwaway PostgreSQL database
    if url:
        engine = create_engine(url)
        SQLModel.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    throttle.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def sent_sms(monkeypatch):
    """Capture outgoing SMS instead of printing them."""
    sent: list[tuple[list[str], str]] = []
    monkeypatch.setattr(sms, "send_sms", lambda phones, msg: sent.append((phones, msg)) or len(phones))
    import routers.shop as shop

    monkeypatch.setattr(shop, "send_sms", sms.send_sms)
    monkeypatch.setattr(shop, "try_send_sms", lambda phones, msg: sent.append((phones, msg)) or True)
    return sent


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client):
    r = client.post(
        "/auth/setup",
        json={"username": "Boss", "full_name": "The Boss", "password": "correct-horse"},
    )
    assert r.status_code == 201, r.text
    return auth(r.json()["access_token"])


@pytest.fixture()
def make_staff(client, admin):
    def _make(username: str, role: str) -> dict:
        r = client.post(
            "/users",
            headers=admin,
            json={"username": username, "full_name": username.title(), "password": "password-123", "role": role},
        )
        assert r.status_code == 201, r.text
        login = client.post("/auth/login", json={"username": username, "password": "password-123"})
        return auth(login.json()["access_token"])

    return _make
