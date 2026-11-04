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
    r1 = new_repair(client, admin, service_fee=3500)
    client.post(f"/repairs/{r1['id']}/parts", headers=admin, json={"name": "Screen", "unit_cost": 3000})
    assert r1["customer_tier"] == "New" and r1["customer_points"] == 0  # nothing collected yet

    collect(client, admin, r1["id"])  # billed 3,500 -> 10 + 35 = 45 points
    again = new_repair(client, admin)  # same customer, new job
    assert (again["customer_visits"], again["customer_points"], again["customer_tier"]) == (1, 45, "Returning")

    for _ in range(2):  # two more 3,500 visits -> 135 points -> Silver
        j = new_repair(client, admin, service_fee=3500)
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


# ---------- optional IMEI ----------
def test_imei_is_optional(client, admin, sent_sms):
    body = {k: v for k, v in INTAKE.items() if k != "imei"}
    missing = client.post("/repairs", headers=admin, json=body)
    blank = client.post("/repairs", headers=admin, json={**body, "phone": "0722000000", "imei": "   "})
    given = client.post("/repairs", headers=admin, json={**body, "phone": "0733000000", "imei": "356938035643809"})
    assert (missing.status_code, blank.status_code, given.status_code) == (201, 201, 201)
    assert missing.json()["imei"] == "" and blank.json()["imei"] == "" and given.json()["imei"] == "356938035643809"
    assert len(client.get("/repairs?q=356938", headers=admin).json()) == 1  # searching by IMEI still works


# ---------- simplified registration ----------
QUICK = {"name": "Amina", "phone": "0712345678", "brand": "Samsung", "model": "Galaxy A14"}


def test_register_service_only_needs_no_money_or_service_type(client, admin, sent_sms):
    r = client.post("/repairs", headers=admin, json=QUICK)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["service_type"] == "Service" and body["imei"] == ""
    assert body["money"]["total"] == 0 and body["money"]["paid"] == 0
    assert client.get(f"/repairs/{body['id']}", headers=admin).json()["parts"] == []


def test_register_with_a_part_creates_the_part_line(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    buy = client.post("/repairs", headers=desk, json={**QUICK, "needs_part": True, "part_name": "A14 screen", "part_source": "purchase"})
    shop = client.post("/repairs", headers=desk, json={**QUICK, "phone": "0722000000", "needs_part": True, "part_name": "Charging port", "part_source": "stock"})
    assert buy.status_code == shop.status_code == 201
    assert buy.json()["service_type"] == "Part replacement"

    part = client.get(f"/repairs/{buy.json()['id']}", headers=admin).json()["parts"][0]
    assert (part["name"], part["source"], part["acquired"], part["added_by"]) == ("A14 screen", "purchase", False, "Dina")
    assert client.get(f"/repairs/{shop.json()['id']}", headers=admin).json()["parts"][0]["acquired"] is True
    stats = client.get("/dashboard", headers=admin).json()
    assert [p["name"] for p in stats["parts_to_buy"]] == ["A14 screen"]  # only the one that must be bought


def test_a_needed_part_must_be_named(client, admin):
    r = client.post("/repairs", headers=admin, json={**QUICK, "needs_part": True, "part_name": "  "})
    assert r.status_code == 422 and "part" in r.text.lower()


# ---------- end-of-day report ----------
def test_end_of_day_summary_lists_jobs_with_service_and_parts(client, admin, sent_sms):
    a = client.post("/repairs", headers=admin, json={**QUICK, "service_fee": 500}).json()["id"]  # service only
    b = client.post("/repairs", headers=admin, json={**QUICK, "phone": "0722000000", "name": "Brian", "needs_part": True,
                                                       "part_name": "Screen", "service_fee": 3500}).json()["id"]
    part = client.get(f"/repairs/{b}", headers=admin).json()["parts"][0]
    client.patch(f"/parts/{part['id']}", headers=admin, json={"unit_cost": 3000})
    for rid in (a, b):
        client.patch(f"/repairs/{rid}", headers=admin, json={"status": "collected"})

    r = client.get("/reports/finance?period=today", headers=admin).json()
    assert (r["service_income"], r["parts_cost"], r["parts_revenue"], r["profit"]) == (4000, 3000, 0, 1000)
    assert (r["repairs_collected"], r["service_only_jobs"], r["jobs_with_parts"]) == (2, 1, 1)
    assert len(r["daily"]) == 1 and r["daily"][0]["service"] == 4000 and r["daily"][0]["parts_cost"] == 3000
    jobs = {j["customer"]: j for j in r["jobs"]}
    assert jobs["Brian"]["parts_cost"] == 3000 and jobs["Brian"]["profit"] == 500 and jobs["Brian"]["had_parts"]
    assert jobs["Amina"]["parts_cost"] == 0 and jobs["Amina"]["service"] == 500 and not jobs["Amina"]["had_parts"]


def test_payment_just_after_midnight_in_nairobi_counts_for_that_day(client, admin, sent_sms):
    """00:30 Nairobi is 21:30 the previous day in UTC. The report must use shop time."""
    from datetime import timedelta

    from database import get_session
    from main import app
    from models import Payment
    from timeutil import period_bounds, shop_tz
    from models import now_utc

    rid = client.post("/repairs", headers=admin, json=QUICK).json()["id"]
    today_start_utc, _ = period_bounds("today", now_utc(), shop_tz())
    session = next(app.dependency_overrides[get_session]())
    session.add(Payment(repair_id=rid, amount=700, created_at=today_start_utc + timedelta(minutes=30)))
    session.add(Payment(repair_id=rid, amount=900, created_at=today_start_utc - timedelta(minutes=30)))  # yesterday
    session.commit()

    r = client.get("/reports/finance?period=today", headers=admin).json()
    assert r["cash_received"] == 700 and r["daily"][0]["cash"] == 700
    assert r["daily"][0]["date"] == today_start_utc.astimezone(shop_tz()).date().isoformat()


def test_dashboard_week_uses_the_same_monday_week_as_finance():
    from datetime import datetime, timezone

    from timeutil import week_start

    wed = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)  # Wednesday morning
    assert week_start(wed) == datetime(2026, 10, 25, 21, 0, tzinfo=timezone.utc)  # Mon 26 Oct 00:00 Nairobi
    sun_night = datetime(2026, 11, 1, 20, 59, tzinfo=timezone.utc)  # still Sunday 23:59 Nairobi
    assert week_start(sun_night) == datetime(2026, 10, 25, 21, 0, tzinfo=timezone.utc)


def test_server_announces_the_shop_timezone_and_sends_utc_dates(client, admin, sent_sms):
    assert client.get("/auth/setup-status").json()["timezone"] == "Africa/Nairobi"
    created = client.post("/repairs", headers=admin, json=QUICK).json()["created_at"]
    assert created.endswith("Z")  # unambiguous UTC, so browsers can convert it correctly


def test_sms_text_has_no_doubled_punctuation(client, admin, sent_sms):
    rid = client.post("/repairs", headers=admin, json=QUICK).json()["id"]
    sent_sms.clear()
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "collected"})
    assert "!." not in sent_sms[0][1] and ".." not in sent_sms[0][1]


# ---------- v8: services, part price at registration, dates, customer delete ----------
def _set_created(client, repair_id, when):
    from database import get_session
    from main import app
    from models import Repair

    session = next(app.dependency_overrides[get_session]())
    r = session.get(Repair, repair_id)
    r.created_at = when
    session.add(r)
    session.commit()


def test_register_with_services_service_fee_and_part_price(client, admin, sent_sms):
    r = client.post("/repairs", headers=admin, json={
        **QUICK, "service_type": "Screen replacement, Software", "service_fee": 500,
        "needs_part": True, "part_name": "A14 screen", "part_source": "purchase", "part_cost": 3000, "part_price": 3500,
    })
    assert r.status_code == 201, r.text
    assert r.json()["service_type"] == "Screen replacement, Software"
    m = r.json()["money"]
    assert (m["service_fee"], m["parts_total"], m["parts_cost"], m["total"], m["profit"]) == (500, 3500, 3000, 4000, 1000)


def test_part_cost_is_not_added_to_the_bill_and_no_part_means_none(client, admin, sent_sms):
    a = client.post("/repairs", headers=admin, json={
        **QUICK, "service_fee": 3000, "needs_part": True, "part_name": "Port", "part_cost": 2000}).json()
    assert (a["money"]["parts_total"], a["money"]["total"], a["money"]["profit"]) == (0, 3000, 1000)
    b = client.post("/repairs", headers=admin, json={**QUICK, "phone": "0722000000", "service_fee": 300}).json()
    assert b["money"]["parts_total"] == 0 and b["money"]["total"] == 300


def test_repairs_filter_and_sort_by_date(client, admin, sent_sms):
    from datetime import timedelta

    from models import now_utc

    ids = [client.post("/repairs", headers=admin, json={**QUICK, "phone": f"07220000{i:02d}"}).json()["id"] for i in range(3)]
    _set_created(client, ids[0], now_utc() - timedelta(days=10))
    _set_created(client, ids[1], now_utc() - timedelta(days=5))
    today = now_utc().date().isoformat()
    five_ago = (now_utc() - timedelta(days=5)).date().isoformat()

    assert [r["id"] for r in client.get("/repairs", headers=admin).json()] == [ids[2], ids[1], ids[0]]
    assert [r["id"] for r in client.get("/repairs?sort=oldest", headers=admin).json()] == [ids[0], ids[1], ids[2]]
    assert {r["id"] for r in client.get(f"/repairs?date_from={five_ago}", headers=admin).json()} == {ids[1], ids[2]}
    assert [r["id"] for r in client.get(f"/repairs?date_from={today}&date_to={today}", headers=admin).json()] == [ids[2]]
    assert client.get(f"/repairs?date_from={today}&date_to={five_ago}", headers=admin).status_code == 422
    assert client.get("/repairs?sort=nonsense", headers=admin).status_code == 422


def test_finance_custom_range_and_all_time(client, admin, sent_sms):
    from datetime import timedelta

    from models import now_utc

    rid = client.post("/repairs", headers=admin, json={**QUICK, "service_fee": 500, "deposit_amount": 500}).json()["id"]
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "collected"})
    today = now_utc().date()
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731

    hit = client.get(f"/reports/finance?period=custom&start={d(-2)}&end={d(1)}", headers=admin).json()
    assert hit["cash_received"] == 500 and hit["service_income"] == 500 and len(hit["daily"]) == 4
    miss = client.get(f"/reports/finance?period=custom&start={d(-9)}&end={d(-3)}", headers=admin).json()
    assert miss["cash_received"] == 0 and miss["repairs_collected"] == 0
    one_day = client.get(f"/reports/finance?period=custom&start={d(0)}&end={d(0)}", headers=admin).json()
    assert one_day["start"] == one_day["end"] and one_day["repairs_collected"] == 1

    everything = client.get("/reports/finance?period=all", headers=admin).json()
    assert everything["service_income"] == 500 and everything["cash_received"] == 500

    assert client.get("/reports/finance?period=custom", headers=admin).status_code == 422
    assert client.get(f"/reports/finance?period=custom&start={d(1)}&end={d(0)}", headers=admin).status_code == 422
    assert client.get(f"/reports/finance?period=custom&start={d(-2000)}&end={d(0)}", headers=admin).status_code == 422


def test_finance_reports_parts_used(client, admin, sent_sms):
    rid = client.post("/repairs", headers=admin, json={**QUICK, "needs_part": True, "part_name": "Screen", "part_cost": 1000}).json()["id"]
    client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "Screws", "quantity": 4, "unit_cost": 10})
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "collected"})
    r = client.get("/reports/finance?period=today", headers=admin).json()
    assert r["parts_used"] == 5 and r["parts_cost"] == 1040


def test_admin_deletes_customer_safely(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    rid = client.post("/repairs", headers=desk, json={**QUICK, "service_fee": 500, "deposit_amount": 200}).json()["id"]
    lone = client.post("/repairs", headers=admin, json={**QUICK, "phone": "0799000111", "name": "Lone"}).json()
    cust = {c["name"]: c["id"] for c in client.get("/customers", headers=admin).json()}

    assert client.delete(f"/customers/{cust['Amina']}", headers=desk).status_code == 403
    guard = client.delete(f"/customers/{cust['Amina']}", headers=admin)
    assert guard.status_code == 409 and "1 repair" in guard.json()["detail"]
    assert client.get(f"/repairs/{rid}", headers=admin).status_code == 200  # nothing was deleted

    done = client.delete(f"/customers/{cust['Amina']}?delete_repairs=true", headers=admin).json()
    assert done == {"ok": True, "repairs": 1, "parts": 0, "payments": 1}
    assert client.get(f"/repairs/{rid}", headers=admin).status_code == 404
    assert {c["name"] for c in client.get("/customers", headers=admin).json()} == {"Lone"}
    assert client.delete("/customers/9999", headers=admin).status_code == 404
    # a customer with no repairs goes without the extra flag
    client.delete(f"/repairs/{lone['id']}", headers=admin)
    assert client.delete(f"/customers/{cust['Lone']}", headers=admin).status_code == 200
