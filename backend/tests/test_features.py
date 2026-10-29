import os

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel, select

INTAKE = {
    "name": "Amina",
    "phone": "0712345678",
    "imei": "356938035643809",
    "brand": "Samsung",
    "model": "Galaxy A14",
    "service_type": "Screen replacement",
}


def new_repair(client, headers, **extra):
    r = client.post("/repairs", headers=headers, json={**INTAKE, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def collect(client, headers, rid):
    return client.patch(f"/repairs/{rid}", headers=headers, json={"status": "collected"})


# ---------- loyalty points ----------
def test_points_and_tiers_come_from_collected_visits(client, admin, sent_sms):
    r1 = new_repair(client, admin, service_fee=500)
    client.post(f"/repairs/{r1['id']}/parts", headers=admin, json={"name": "Screen", "unit_cost": 3000})
    assert r1["customer_tier"] == "New" and r1["customer_points"] == 0  # nothing collected yet

    collect(client, admin, r1["id"])  # billed 3,500 -> 10 + 35 = 45 points
    again = new_repair(client, admin)  # same customer, new job
    assert (again["customer_visits"], again["customer_points"], again["customer_tier"]) == (1, 45, "Returning")

    for _ in range(2):  # two more 3,500 visits -> 135 points -> Silver
        j = new_repair(client, admin, service_fee=500)
        client.post(f"/repairs/{j['id']}/parts", headers=admin, json={"name": "Screen", "unit_cost": 3000})
        collect(client, admin, j["id"])
    assert new_repair(client, admin)["customer_tier"] == "Silver"


def test_failed_repairs_earn_no_points(client, admin, sent_sms):
    rid = new_repair(client, admin, service_fee=500)["id"]
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "incomplete", "reason": "Board is dead"})
    collect(client, admin, rid)
    assert new_repair(client, admin)["customer_points"] == 0


def test_technician_sees_tier_but_no_phone_or_spend(client, admin, make_staff, sent_sms):
    tech = make_staff("tom", "technician")
    new_repair(client, admin)
    row = client.get("/repairs", headers=tech).json()[0]
    assert row["customer_phone"] is None and row["money"] is None and row["customer_tier"] == "New"
    assert client.get("/repairs", headers=admin).json()[0]["customer_phone"] == "+254712345678"
    assert client.get("/customers", headers=tech).status_code == 403


# ---------- customer directory & lookup ----------
def test_customer_list_has_stats_and_search(client, admin, sent_sms):
    a = new_repair(client, admin, service_fee=500)["id"]
    collect(client, admin, a)
    new_repair(client, admin, phone="0722000000", name="Brian")
    rows = {c["name"]: c for c in client.get("/customers", headers=admin).json()}
    assert rows["Amina"]["visits"] == 1 and rows["Amina"]["total_spent"] == 500 and rows["Amina"]["points"] == 15
    assert rows["Brian"]["repairs"] == 1 and rows["Brian"]["visits"] == 0
    assert [c["name"] for c in client.get("/customers?q=bri", headers=admin).json()] == ["Brian"]
    assert [c["name"] for c in client.get("/customers?q=%2B254712", headers=admin).json()] == ["Amina"]


def test_phone_lookup_fills_in_returning_customers(client, admin, sent_sms):
    new_repair(client, admin)
    hit = client.get("/customers/lookup?phone=0712%20345%20678", headers=admin).json()  # any format
    assert hit["found"] is True and hit["name"] == "Amina"
    assert client.get("/customers/lookup?phone=0799999999", headers=admin).json()["found"] is False
    assert client.get("/customers/lookup?phone=abc", headers=admin).json()["found"] is False


# ---------- "could not complete" ----------
def test_incomplete_requires_a_reason(client, admin, make_staff, sent_sms):
    tech = make_staff("tom", "technician")
    rid = new_repair(client, admin)["id"]
    for body in ({"status": "incomplete"}, {"status": "incomplete", "reason": "   "}):
        r = client.patch(f"/repairs/{rid}", headers=tech, json=body)
        assert r.status_code == 422 and "explain" in r.json()["detail"]

    ok = client.patch(f"/repairs/{rid}", headers=tech, json={"status": "incomplete", "reason": "Motherboard water damage"})
    assert ok.status_code == 200
    assert ok.json()["failure_reason"] == "Motherboard water damage" and ok.json()["failure_by"] == "Tom"
    assert any("could not be fully repaired" in msg for _, msg in sent_sms)

    # the note survives other edits and the customer collecting the phone
    assert client.patch(f"/repairs/{rid}", headers=tech, json={"progress": 40}).json()["failure_reason"]
    assert collect(client, admin, rid).json()["failure_reason"] == "Motherboard water damage"


def test_resuming_work_clears_the_note_and_it_stays_internal(client, admin, sent_sms):
    rid = new_repair(client, admin)["id"]
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "incomplete", "reason": "Part unavailable"})
    code = client.get(f"/repairs/{rid}", headers=admin).json()["ticket_code"]
    public = client.get(f"/track/{code}").json()
    assert public["status"] == "incomplete" and "Part unavailable" not in str(public)
    assert client.patch(f"/repairs/{rid}", headers=admin, json={"status": "repairing"}).json()["failure_reason"] == ""
    assert client.get("/dashboard", headers=admin).json()["incomplete"] == 0


def test_incomplete_jobs_leave_the_buy_list(client, admin, sent_sms):
    rid = new_repair(client, admin)["id"]
    client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "Screen", "source": "purchase"})
    assert client.get("/dashboard", headers=admin).json()["parts_to_buy_count"] == 1
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "incomplete", "reason": "Customer declined"})
    assert client.get("/dashboard", headers=admin).json()["parts_to_buy_count"] == 0


# ---------- admin-only deletes ----------
def test_admin_deletes_staff(client, admin, make_staff):
    tom = make_staff("tom", "technician")
    mary = make_staff("mary", "manager")
    users = {u["username"]: u for u in client.get("/users", headers=admin).json()}
    assert client.delete(f"/users/{users['tom']['id']}", headers=mary).status_code == 403
    assert client.delete(f"/users/{users['boss']['id']}", headers=admin).status_code == 400  # not yourself
    assert client.delete("/users/9999", headers=admin).status_code == 404
    assert client.delete(f"/users/{users['tom']['id']}", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=tom).status_code == 401  # their session dies immediately
    assert "tom" not in {u["username"] for u in client.get("/users", headers=admin).json()}


def test_admin_deletes_repair_with_parts_and_payments(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    rid = new_repair(client, desk, service_fee=500, deposit_amount=1000)["id"]
    client.post(f"/repairs/{rid}/parts", headers=desk, json={"name": "Screen", "unit_cost": 3000})
    assert client.delete(f"/repairs/{rid}", headers=desk).status_code == 403
    assert client.get(f"/repairs/{rid}", headers=admin).status_code == 200

    r = client.delete(f"/repairs/{rid}", headers=admin)
    assert r.json() == {"ok": True, "parts": 1, "payments": 1}
    assert client.get(f"/repairs/{rid}", headers=admin).status_code == 404
    assert client.delete(f"/repairs/{rid}", headers=admin).status_code == 404
    assert client.get("/reports/finance?period=today", headers=admin).json()["cash_received"] == 0
    assert client.get("/customers", headers=admin).json()[0]["repairs"] == 0  # customer is kept


# ---------- legacy phone numbers are merged ----------
def test_old_phone_formats_are_normalised_and_merged(tmp_path, monkeypatch):
    import database
    from models import Customer, Repair

    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        for i, phone in enumerate(["0712345678", "+254712345678", "254712345678", "0799000111", "n/a"], start=1):
            s.add(Customer(id=i, name=f"C{i}", phone=phone))
        s.commit()
        for i, cid in enumerate([1, 2, 3, 4], start=1):
            s.add(Repair(ticket_code=f"T{i}", customer_id=cid, imei="1", brand="X", model="Y", service_type="Z"))
        s.commit()

    monkeypatch.setattr(database, "engine", eng)
    database.normalise_customer_phones()
    database.normalise_customer_phones()  # safe to repeat

    with Session(eng) as s:
        phones = sorted(c.phone for c in s.exec(select(Customer)))
        assert phones == ["+254712345678", "+254799000111", "n/a"]  # three duplicates became one
        keeper = s.exec(select(Customer).where(Customer.phone == "+254712345678")).one()
        assert keeper.id == 1
        assert sorted(r.ticket_code for r in s.exec(select(Repair).where(Repair.customer_id == 1))) == ["T1", "T2", "T3"]


def test_old_sqlite_gets_the_new_columns(tmp_path, monkeypatch):
    import database

    eng = create_engine(f"sqlite:///{tmp_path / 'v3.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE repair (id INTEGER PRIMARY KEY, status TEXT, updated_at DATETIME)"))
    monkeypatch.setattr(database, "engine", eng)
    database._add_missing_columns()
    with eng.begin() as c:
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(repair)"))}
    assert {"service_fee", "collected_at", "failure_reason", "failure_by"} <= cols


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs a throwaway PostgreSQL database")
def test_postgres_enum_gets_the_new_status(monkeypatch):
    """The real upgrade path: a database created before 'incomplete' existed."""
    import database

    eng = create_engine(os.environ["TEST_DATABASE_URL"])
    SQLModel.metadata.drop_all(eng)
    with eng.begin() as c:
        c.execute(text("DROP TYPE IF EXISTS status CASCADE"))
        c.execute(text("CREATE TYPE status AS ENUM ('received','diagnosing','waiting_parts','repairing','ready','collected')"))
        c.execute(text(
            "CREATE TABLE repair (id SERIAL PRIMARY KEY, ticket_code VARCHAR, customer_id INTEGER, imei VARCHAR, brand VARCHAR,"
            " model VARCHAR, service_type VARCHAR, service_details VARCHAR, assigned_to VARCHAR, status status, progress INTEGER,"
            " estimated_completion TIMESTAMP, created_at TIMESTAMP, updated_at TIMESTAMP, service_fee INTEGER NOT NULL DEFAULT 0)"
        ))
        c.execute(text(
            "INSERT INTO repair (ticket_code, customer_id, imei, brand, model, service_type, service_details, assigned_to,"
            " status, progress, created_at, updated_at) VALUES ('OLD1',1,'1','X','Y','Z','','','collected',100,now(),now())"
        ))
    monkeypatch.setattr(database, "engine", eng)
    database.init_db()
    database.init_db()  # idempotent
    with eng.begin() as c:
        c.execute(text("UPDATE repair SET status = 'incomplete', failure_reason = 'x' WHERE ticket_code = 'OLD1'"))
        row = c.execute(text("SELECT status::text, collected_at IS NOT NULL FROM repair")).one()
    assert tuple(row) == ("incomplete", True)  # old collected job was back-filled too
    SQLModel.metadata.drop_all(eng)
    with eng.begin() as c:
        c.execute(text("DROP TYPE IF EXISTS status CASCADE"))
