import sqlite3

from sqlalchemy import create_engine

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


# ---------- intake charges ----------
def test_intake_records_service_fee_and_deposit(client, admin, sent_sms):
    repair = new_repair(client, admin, service_fee=500, deposit_amount=1000, deposit_method="mpesa")
    assert repair["money"]["service_fee"] == 500
    assert repair["money"]["paid"] == 1000 and repair["money"]["balance"] == -500
    detail = client.get(f"/repairs/{repair['id']}", headers=admin).json()
    assert detail["payments"][0]["method"] == "mpesa" and detail["payments"][0]["amount"] == 1000


# ---------- the worked example: 3,500 = 500 service + 3,000 part ----------
def test_price_breakdown_and_profit(client, admin, sent_sms):
    repair = new_repair(client, admin, service_fee=500)
    part = client.post(
        f"/repairs/{repair['id']}/parts",
        headers=admin,
        json={"name": "A14 screen", "source": "purchase", "unit_cost": 3000},
    )
    assert part.status_code == 201
    assert part.json()["unit_price"] == 3000 and part.json()["acquired"] is False  # price follows cost

    money = client.get(f"/repairs/{repair['id']}", headers=admin).json()["money"]
    assert money == {
        "service_fee": 500, "parts_total": 3000, "parts_cost": 3000,
        "total": 3500, "paid": 0, "balance": 3500, "profit": 500,
    }


def test_markup_on_parts_counts_as_profit(client, admin, sent_sms):
    repair = new_repair(client, admin, service_fee=500)
    client.post(f"/repairs/{repair['id']}/parts", headers=admin,
                json={"name": "Battery", "quantity": 2, "unit_cost": 800, "unit_price": 1000})
    money = client.get(f"/repairs/{repair['id']}", headers=admin).json()["money"]
    assert money["total"] == 2500 and money["parts_cost"] == 1600 and money["profit"] == 900


# ---------- who sees / does what ----------
def test_technician_adds_parts_but_sees_no_money(client, admin, make_staff, sent_sms):
    tech = make_staff("tom", "technician")
    repair = new_repair(client, admin, service_fee=500)
    rid = repair["id"]

    added = client.post(f"/repairs/{rid}/parts", headers=tech, json={"name": "Screen", "source": "purchase"})
    assert added.status_code == 201
    assert added.json()["unit_cost"] is None and added.json()["unit_price"] is None

    assert client.post(f"/repairs/{rid}/parts", headers=tech, json={"name": "X", "unit_cost": 5}).status_code == 403
    assert client.patch(f"/parts/{added.json()['id']}", headers=tech, json={"unit_price": 9}).status_code == 403
    assert client.patch(f"/repairs/{rid}", headers=tech, json={"service_fee": 1}).status_code == 403
    assert client.post(f"/repairs/{rid}/payments", headers=tech, json={"amount": 100}).status_code == 403

    detail = client.get(f"/repairs/{rid}", headers=tech).json()
    assert detail["money"] is None and detail["payments"] == []
    assert all(r["money"] is None for r in client.get("/repairs", headers=tech).json())
    assert "service_fee" not in detail


def test_profit_is_admin_only(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    repair = new_repair(client, desk, service_fee=500)
    assert repair["money"] is not None and repair["money"]["profit"] is None
    assert client.get("/reports/finance", headers=desk).status_code == 403


def test_cost_edit_updates_price_only_when_sold_at_cost(client, admin, sent_sms):
    rid = new_repair(client, admin)["id"]
    part = client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "Port", "unit_cost": 100}).json()
    assert client.patch(f"/parts/{part['id']}", headers=admin, json={"unit_cost": 150}).json()["unit_price"] == 150
    client.patch(f"/parts/{part['id']}", headers=admin, json={"unit_price": 300})
    assert client.patch(f"/parts/{part['id']}", headers=admin, json={"unit_cost": 200}).json()["unit_price"] == 300


def test_collected_jobs_are_locked_for_non_admins(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    rid = new_repair(client, desk, service_fee=500)["id"]
    part = client.post(f"/repairs/{rid}/parts", headers=desk, json={"name": "Glass"}).json()
    client.patch(f"/repairs/{rid}", headers=desk, json={"status": "collected"})
    assert client.delete(f"/parts/{part['id']}", headers=desk).status_code == 409
    assert client.patch(f"/repairs/{rid}", headers=desk, json={"service_fee": 9}).status_code == 409
    assert client.delete(f"/parts/{part['id']}", headers=admin).status_code == 200


def test_only_admin_deletes_payments(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    rid = new_repair(client, desk)["id"]
    pay = client.post(f"/repairs/{rid}/payments", headers=desk, json={"amount": 500, "method": "cash"})
    assert pay.status_code == 201 and pay.json()["received_by"] == "Dina"
    assert client.delete(f"/payments/{pay.json()['id']}", headers=desk).status_code == 403
    assert client.delete(f"/payments/{pay.json()['id']}", headers=admin).status_code == 200


def test_validation(client, admin, sent_sms):
    rid = new_repair(client, admin)["id"]
    assert client.post(f"/repairs/{rid}/payments", headers=admin, json={"amount": 0}).status_code == 422
    assert client.post(f"/repairs/{rid}/payments", headers=admin, json={"amount": -5}).status_code == 422
    assert client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "  "}).status_code == 422
    assert client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "x", "quantity": 0}).status_code == 422
    assert client.post("/repairs/999/parts", headers=admin, json={"name": "x"}).status_code == 404


# ---------- dashboard parts queue ----------
def test_parts_to_buy_queue(client, admin, sent_sms):
    rid = new_repair(client, admin)["id"]
    buy = client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "Screen", "source": "purchase"}).json()
    client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "Screws", "source": "stock"})
    stats = client.get("/dashboard", headers=admin).json()
    assert [p["name"] for p in stats["parts_to_buy"]] == ["Screen"] and stats["parts_to_buy_count"] == 1
    client.patch(f"/parts/{buy['id']}", headers=admin, json={"acquired": True})
    assert client.get("/dashboard", headers=admin).json()["parts_to_buy_count"] == 0


# ---------- finance report ----------
def test_finance_report_week(client, admin, sent_sms):
    # Job 1: 500 service + 3000 part, fully paid, collected -> profit 500
    a = new_repair(client, admin, service_fee=500, deposit_amount=1000, deposit_method="mpesa")["id"]
    client.post(f"/repairs/{a}/parts", headers=admin, json={"name": "Screen", "unit_cost": 3000})
    client.post(f"/repairs/{a}/payments", headers=admin, json={"amount": 2500, "method": "cash"})
    client.patch(f"/repairs/{a}", headers=admin, json={"status": "collected"})
    # Job 2: still open, 2000 service, unpaid -> counts as outstanding, not profit
    new_repair(client, admin, phone="0722000000", service_fee=2000)

    r = client.get("/reports/finance?period=week", headers=admin).json()
    assert r["cash_received"] == 3500 and r["payments_count"] == 2
    assert r["by_method"] == {"mpesa": 1000, "cash": 2500}
    assert r["repairs_collected"] == 1
    assert (r["service_income"], r["parts_revenue"], r["parts_cost"], r["profit"]) == (500, 3000, 3000, 500)
    assert (r["outstanding"], r["outstanding_count"]) == (2000, 1)
    assert r["parts_without_cost"] == 0
    assert len(r["daily"]) == 7 and sum(d["cash"] for d in r["daily"]) == 3500
    assert sum(d["profit"] for d in r["daily"]) == 500

    assert client.get("/reports/finance?period=last_week", headers=admin).json()["cash_received"] == 0
    assert client.get("/reports/finance?period=nonsense", headers=admin).status_code == 422


def test_report_flags_parts_missing_a_cost(client, admin, sent_sms):
    rid = new_repair(client, admin, service_fee=500)["id"]
    client.post(f"/repairs/{rid}/parts", headers=admin, json={"name": "Mystery part"})
    client.patch(f"/repairs/{rid}", headers=admin, json={"status": "collected"})
    assert client.get("/reports/finance?period=today", headers=admin).json()["parts_without_cost"] == 1


def test_period_bounds_use_monday_weeks():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from routers.reports import period_bounds

    tz = ZoneInfo("Africa/Nairobi")
    sunday_night_utc = datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc)  # already Monday 01:00 in Nairobi
    start, end = period_bounds("week", sunday_night_utc, tz)
    assert start == datetime(2026, 10, 25, 21, 0, tzinfo=timezone.utc)  # Mon 26 Oct 00:00 Nairobi
    assert (end - start).days == 7
    ms, me = period_bounds("month", sunday_night_utc, tz)
    assert ms.astimezone(tz).day == 1 and me.astimezone(tz).month == 11


# ---------- upgrading an existing v2 database ----------
def test_old_database_is_upgraded_in_place(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE customer (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, created_at DATETIME);
        CREATE TABLE repair (id INTEGER PRIMARY KEY, ticket_code TEXT, customer_id INTEGER, imei TEXT, brand TEXT,
            model TEXT, service_type TEXT, service_details TEXT, assigned_to TEXT, status TEXT, progress INTEGER,
            estimated_completion DATETIME, created_at DATETIME, updated_at DATETIME);
        INSERT INTO repair (id, ticket_code, customer_id, imei, brand, model, service_type, service_details,
            assigned_to, status, progress, created_at, updated_at)
            VALUES (1,'AAAAAA',1,'1','X','Y','Z','','','collected',100,'2026-10-01 10:00:00','2026-10-02 12:00:00'),
                   (2,'BBBBBB',1,'1','X','Y','Z','','','received',0,'2026-10-01 10:00:00','2026-10-01 10:00:00');
        """
    )
    con.commit()
    con.close()

    import database

    monkeypatch.setattr(database, "engine", create_engine(f"sqlite:///{db}"))
    database.init_db()
    database.init_db()  # idempotent

    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT id, collected_at FROM repair").fetchall())
    assert rows[1] == "2026-10-02 12:00:00" and rows[2] is None  # old collected jobs are backfilled
    assert con.execute("SELECT service_fee FROM repair WHERE id = 2").fetchone() == (0,)
    assert {"part", "payment"} <= {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
