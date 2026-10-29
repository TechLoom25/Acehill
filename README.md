# Acehill Repair

Repair shop manager: customer intake, repair tracking, SMS notifications, bulk SMS,
and staff accounts with roles.

## Run the backend

    cd backend
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env                                # Windows: copy .env.example .env
    uvicorn main:app --reload                           # http://127.0.0.1:8000/docs

## Run the frontend

    cd frontend
    npm install
    npm run dev        # http://localhost:5173

## First run

Open http://localhost:5173. With no users yet you land on the **setup screen** to create the
administrator. After that, sign in normally and add staff under **Staff**.
(Optional: set `SETUP_KEY` in `backend/.env` so only someone who knows it can create the first admin.)

## Roles

| Capability               | Admin | Manager | Front desk | Technician |
| ------------------------ | :---: | :-----: | :--------: | :--------: |
| Dashboard, view repairs  |   ✓   |    ✓    |     ✓      |     ✓      |
| Update repair status     |   ✓   |    ✓    |     ✓      |     ✓      |
| Register new repairs     |   ✓   |    ✓    |     ✓      |            |
| Customer list            |   ✓   |    ✓    |     ✓      |            |
| List parts on a repair   |   ✓   |    ✓    |     ✓      |     ✓      |
| See prices, enter part costs, take payments | ✓ | ✓ | ✓ |        |
| Finance report & profit  |   ✓   |         |            |            |
| Delete a payment, repair or staff account | ✓ | | | |
| Bulk SMS                 |   ✓   |    ✓    |            |            |
| Manage staff accounts    |   ✓   |         |            |            |

## Customers & loyalty

Customers earn **experience points** from completed visits: 10 per visit plus 1 for every KES 100 billed.
Tiers: Returning (10+), Silver (100+), Gold (300+), Platinum (600+). Points are calculated from history, never stored,
so they cannot drift. Repairs marked "could not complete" earn nothing. Typing a phone number on the New repair form
looks up the saved customer and fills in the name. Tune the rules in `backend/loyalty.py`.

## Repairs that can't be completed

Any staff member can set a repair to **Could not complete**; a written reason is mandatory. The reason is internal
(never shown on the public tracking page) and is kept when the customer collects the phone. Moving the job back to
work clears it.

## Deleting

Administrators can permanently delete staff accounts, repairs (with their parts and payments) and payments. Deletions
are written to the server log (`journalctl -u acehill-backend | grep audit`). Prefer *disabling* a staff account if you
may need it again.

## Money

* Each repair has a **service fee** (labour) plus **parts**. Each part has a *cost* (what it cost the shop) and a *price*
  (what the customer pays; blank = same as cost). Total = service fee + parts prices.
* Parts are either **from shop stock** or **to be purchased** (these show on the dashboard until marked bought).
* Payments (deposit at intake, balance at pickup) are recorded per repair with the method.
* **Finance** (admin only): *cash received* counts payments taken in the period; *profit* counts jobs **collected**
  in the period (service fee + parts charged − parts cost). Weeks run Monday–Sunday in `SHOP_TIMEZONE`.
* Collected repairs are locked for everyone except admins. Technicians never see prices or costs.
* Amounts are whole shillings (KES).

`/track` is public: customers look up a ticket code and see no personal data.

## SMS

Without `AT_API_KEY`, messages print in the backend console. Set `AT_USERNAME` / `AT_API_KEY`
(Africa's Talking) to send real SMS.

## Deploying

See [`deploy/DEPLOY.md`](deploy/DEPLOY.md): nginx + PostgreSQL on a DigitalOcean droplet, HTTPS, backups.

## Tests

    cd backend
    pip install -r requirements-dev.txt
    pytest

## Upgrading from v2

Restart the backend. It adds the new columns/tables to your existing database automatically (back up `acehill.db` first
if it holds real data). Old collected repairs are back-filled so they appear in reports.

## Upgrading from the ADMIN_KEY version

`ADMIN_KEY` is gone. Your existing `acehill.db` keeps all customers and repairs; the new `user`
table is created automatically and the setup screen appears on next launch.
