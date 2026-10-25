import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Notice, PageHeader } from "../components/ui.jsx";
import StaffDatalist from "../components/StaffDatalist.jsx";
import { PAYMENT_METHODS, SERVICE_TYPES, money, toAmount } from "../lib.js";

const empty = {
  name: "", phone: "", imei: "", brand: "", model: "", service_type: "", service_details: "", assigned_to: "",
  service_fee: "", deposit_amount: "", deposit_method: "cash",
};

export default function NewRepair() {
  const navigate = useNavigate();
  const [f, setF] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api("/repairs", {
        method: "POST",
        body: { ...f, service_fee: toAmount(f.service_fee), deposit_amount: toAmount(f.deposit_amount) },
      });
      const sms = r.sms_sent ? "Confirmation SMS sent." : "The confirmation SMS could not be sent, so give the customer the ticket code.";
      const deposit = r.money?.paid ? ` Deposit of ${money(r.money.paid)} recorded.` : "";
      // Land on the job so parts can be listed straight away.
      navigate(`/repairs/${r.id}`, { state: { flash: { type: "ok", text: `Registered. Ticket ${r.ticket_code}.${deposit} ${sms}` } } });
    } catch (ex) {
      setError({ type: "err", text: ex.message });
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="New repair" subtitle="Register the device, agree the charges and notify the customer by SMS.">
        <Link to="/repairs" className="btn ghost">View repairs</Link>
      </PageHeader>
      <form className="card stack" onSubmit={submit}>
        <h2>Customer</h2>
        <div className="grid">
          <label>Customer name<input value={f.name} onChange={set("name")} required /></label>
          <label>Phone number<input value={f.phone} onChange={set("phone")} placeholder="0712 345 678" inputMode="tel" required minLength={5} /></label>
        </div>

        <h2>Device & service</h2>
        <div className="grid">
          <label>IMEI number<input value={f.imei} onChange={set("imei")} inputMode="numeric" required /></label>
          <label>Brand<input value={f.brand} onChange={set("brand")} placeholder="Samsung" required /></label>
          <label>Model<input value={f.model} onChange={set("model")} placeholder="Galaxy A14" required /></label>
          <label>Type of service
            <select value={f.service_type} onChange={set("service_type")} required>
              <option value="">Select…</option>
              {SERVICE_TYPES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label>Assigned technician
            <input list="staff-names" value={f.assigned_to} onChange={set("assigned_to")} placeholder="Optional" />
          </label>
        </div>
        <StaffDatalist />
        <label>Issue details
          <textarea value={f.service_details} onChange={set("service_details")} maxLength={2000} />
        </label>

        <h2>Charges</h2>
        <p className="muted small" style={{ margin: "-8px 0 0" }}>
          The service fee is your labour charge. Parts are added to the job afterwards by the technician, and their price is added to the total.
        </p>
        <div className="grid">
          <label>Service fee (KES)
            <input type="number" min="0" step="1" inputMode="numeric" value={f.service_fee} onChange={set("service_fee")} placeholder="0" />
          </label>
          <label>Deposit paid now (KES)
            <input type="number" min="0" step="1" inputMode="numeric" value={f.deposit_amount} onChange={set("deposit_amount")} placeholder="0" />
          </label>
          <label>Deposit method
            <select value={f.deposit_method} onChange={set("deposit_method")} disabled={!toAmount(f.deposit_amount)}>
              {PAYMENT_METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        </div>

        <Notice n={error} />
        <div><button className="btn" disabled={busy}>{busy ? "Saving…" : "Register & notify customer"}</button></div>
      </form>
    </>
  );
}
