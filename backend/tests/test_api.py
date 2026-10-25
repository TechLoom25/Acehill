INTAKE = {
    "name": "Amina",
    "phone": "+254700000001",
    "imei": "356938035643809",
    "brand": "Samsung",
    "model": "Galaxy A14",
    "service_type": "Screen replacement",
}


# ---------- first-run setup ----------
def test_setup_flow_runs_once(client):
    assert client.get("/auth/setup-status").json()["needs_setup"] is True
    body = {"username": "  Boss ", "full_name": "The Boss", "password": "correct-horse"}
    r = client.post("/auth/setup", json=body)
    assert r.status_code == 201
    assert r.json()["user"]["username"] == "boss"  # trimmed + lower-cased
    assert r.json()["user"]["role"] == "admin"
    assert client.get("/auth/setup-status").json()["needs_setup"] is False
    assert client.post("/auth/setup", json=body).status_code == 409


def test_setup_rejects_weak_input(client):
    r = client.post("/auth/setup", json={"username": "a", "full_name": "x", "password": "short"})
    assert r.status_code == 422


# ---------- login ----------
def test_login_and_me(client, admin):
    r = client.post("/auth/login", json={"username": "BOSS", "password": "correct-horse"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["full_name"] == "The Boss"


def test_bad_credentials_are_generic(client, admin):
    wrong_pw = client.post("/auth/login", json={"username": "boss", "password": "nope-nope"})
    no_user = client.post("/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_login_is_throttled(client, admin):
    for _ in range(5):
        client.post("/auth/login", json={"username": "boss", "password": "wrong-wrong"})
    r = client.post("/auth/login", json={"username": "boss", "password": "correct-horse"})
    assert r.status_code == 429


def test_requests_without_token_are_rejected(client):
    assert client.get("/repairs").status_code == 401
    assert client.get("/repairs", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_disabled_user_is_locked_out_immediately(client, admin, make_staff):
    tech = make_staff("tom", "technician")
    users = client.get("/users", headers=admin).json()
    tom = next(u for u in users if u["username"] == "tom")
    client.patch(f"/users/{tom['id']}", headers=admin, json={"is_active": False})
    assert client.get("/auth/me", headers=tech).status_code == 401
    assert client.post("/auth/login", json={"username": "tom", "password": "password-123"}).status_code == 403


# ---------- roles ----------
def test_only_admin_manages_staff(client, make_staff):
    manager = make_staff("mary", "manager")
    assert client.get("/users", headers=manager).status_code == 403
    r = client.post(
        "/users",
        headers=manager,
        json={"username": "x-user", "full_name": "X", "password": "password-123", "role": "admin"},
    )
    assert r.status_code == 403


def test_duplicate_username_conflicts(client, admin):
    body = {"username": "dup", "full_name": "Dup", "password": "password-123", "role": "technician"}
    assert client.post("/users", headers=admin, json=body).status_code == 201
    assert client.post("/users", headers=admin, json=body).status_code == 409


def test_admin_cannot_demote_or_disable_self(client, admin):
    me = client.get("/auth/me", headers=admin).json()
    assert client.patch(f"/users/{me['id']}", headers=admin, json={"role": "technician"}).status_code == 400
    assert client.patch(f"/users/{me['id']}", headers=admin, json={"is_active": False}).status_code == 400
    assert client.patch(f"/users/{me['id']}", headers=admin, json={"full_name": "Renamed"}).status_code == 200


def test_technician_can_update_but_not_create_repairs(client, admin, make_staff, sent_sms):
    desk = make_staff("dina", "front_desk")
    tech = make_staff("tom", "technician")
    assert client.post("/repairs", headers=tech, json=INTAKE).status_code == 403
    created = client.post("/repairs", headers=desk, json=INTAKE)
    assert created.status_code == 201
    repair = created.json()
    assert repair["customer_name"] == "Amina" and repair["sms_sent"] is True

    r = client.patch(f"/repairs/{repair['id']}", headers=tech, json={"status": "ready", "progress": 100})
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert any("READY" in msg for _, msg in sent_sms)
    assert client.get("/customers", headers=tech).status_code == 403
    assert client.post("/sms/bulk", headers=tech, json={"message": "hi"}).status_code == 403


def test_progress_is_validated(client, admin, sent_sms):
    repair = client.post("/repairs", headers=admin, json=INTAKE).json()
    r = client.patch(f"/repairs/{repair['id']}", headers=admin, json={"progress": 150})
    assert r.status_code == 422


# ---------- bulk SMS ----------
def test_bulk_sms_empty_selection_does_not_message_everyone(client, admin, sent_sms):
    client.post("/repairs", headers=admin, json=INTAKE)
    sent_sms.clear()
    r = client.post("/sms/bulk", headers=admin, json={"message": "Sale!", "phones": []})
    assert r.status_code == 400 and not sent_sms


def test_bulk_sms_only_reaches_registered_customers(client, admin, sent_sms):
    client.post("/repairs", headers=admin, json=INTAKE)
    sent_sms.clear()
    r = client.post(
        "/sms/bulk", headers=admin, json={"message": "Hi", "phones": [INTAKE["phone"], "+254799999999"]}
    )
    assert r.json() == {"sent_to": 1, "failed": 0}
    assert sent_sms == [([INTAKE["phone"]], "Hi")]


# ---------- tracking, search, dashboard ----------
def test_public_tracking_hides_personal_data(client, admin, sent_sms):
    code = client.post("/repairs", headers=admin, json=INTAKE).json()["ticket_code"]
    r = client.get(f"/track/{code.lower()}")  # no auth header
    assert r.status_code == 200
    assert set(r.json()) == {"ticket_code", "device", "status", "progress", "estimated_completion", "updated_at"}
    assert client.get("/track/NOPE00").status_code == 404


def test_search_and_dashboard(client, admin, sent_sms):
    client.post("/repairs", headers=admin, json=INTAKE)
    client.post("/repairs", headers=admin, json={**INTAKE, "phone": "+254700000002", "name": "Brian", "brand": "Tecno"})
    assert len(client.get("/repairs?q=tecno", headers=admin).json()) == 1
    assert len(client.get("/repairs?q=amina", headers=admin).json()) == 1
    assert client.get("/repairs?q=%25", headers=admin).json() == []  # wildcard is escaped

    stats = client.get("/dashboard", headers=admin).json()
    assert stats["open"] == 2 and stats["customers"] == 2 and stats["new_this_week"] == 2
    assert stats["by_status"]["received"] == 2
    assert stats["workload"] == [{"name": "Unassigned", "open": 2}]
    assert len(stats["recent"]) == 2


# ---------- phone numbers ----------
def test_phone_numbers_are_normalised(client, admin, sent_sms):
    for raw in ["0712 345 678", "254712345678", "712345678", "+254-712-345-678"]:
        r = client.post("/repairs", headers=admin, json={**INTAKE, "phone": raw})
        assert r.status_code == 201, raw
    customers = client.get("/customers", headers=admin).json()
    assert [c["phone"] for c in customers] == ["+254712345678"]  # all four are one customer


def test_invalid_phone_is_rejected(client, admin):
    r = client.post("/repairs", headers=admin, json={**INTAKE, "phone": "abc12345"})
    assert r.status_code == 422
