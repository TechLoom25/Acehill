import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Notice, PageHeader, TierBadge } from "../components/ui.jsx";
import StaffDatalist from "../components/StaffDatalist.jsx";
import { SERVICE_TYPES, money, toAmount } from "../lib.js";

const empty = {
  name: "", phone: "", brand: "", model: "", imei: "", service_details: "", assigned_to: "",
  services: [], service_fee: "",
  needs_part: false, part_name: "", part_source: "", part_cost: "", part_price: "",
};

export default function NewRepair() {
  const [f, setF] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const [known, setKnown] = useState(null);
  const nameRef = useRef(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggleService = (s) =>
    setF({ ...f, services: f.services.includes(s) ? f.services.filter((x) => x !== s) : [...f.services, s] });

  // Look the number up as it is typed and fill in the saved name if none was typed.
  useEffect(() => {
    const phone = f.phone.trim();
    if (phone.replace(/\D/g, "").length < 9) {
      setKnown(null);
      return;
    }
    let alive = true;
    const t = setTimeout(() => {
      api(`/customers/lookup?phone=${encodeURIComponent(phone)}`)
        .then((r) => {
          if (!alive) return;
          setKnown(r.found ? r : null);
          if (r.found) setF((cur) => (cur.name.trim() ? cur : { ...cur, name: r.name }));
        })
        .catch(() => alive && setKnown(null));
    }, 350);
    return () => { alive = false; clearTimeout(t); };
  }, [f.phone]);

  async function submit(e) {
    e.preventDefault();
    if (!f.services.length) return setError({ type: "err", text: "Choose at least one service." });
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: f.name, phone: f.phone, brand: f.brand, model: f.model, imei: f.imei,
        service_details: f.service_details, assigned_to: f.assigned_to,
        service_type: f.services.join(", "),
        service_fee: toAmount(f.service_fee),
        needs_part: f.needs_part,
        part_name: f.needs_part ? f.part_name : "",
        part_source: f.part_source || "purchase",
        part_cost: f.needs_part ? toAmount(f.part_cost) : 0,
        part_price: f.needs_part && f.part_price !== "" ? toAmount(f.part_price) : null,
      };
      const r = await api("/repairs", { method: "POST", body });
      setDone(r);
      setF(empty);
      setKnown(null);
      nameRef.current?.focus();
    } catch (ex) {
      setError({ type: "err", text: ex.message });
    }
    setBusy(false);
  }

  const total = toAmount(f.service_fee) + (f.needs_part ? toAmount(f.part_price !== "" ? f.part_price : f.part_cost) : 0);

  return (
    <>
      <PageHeader title="Register a phone" subtitle="Check the customer in, choose the services, and enter what you are charging.">
        <Link to="/repairs" className="btn ghost">View repairs</Link>
      </PageHeader>

      {done && (
        <div className="msg ok">
          <strong>Registered. Ticket {done.ticket_code}</strong> for {done.brand} {done.model} ({done.customer_name}).{" "}
          {done.sms_sent ? "Confirmation SMS sent." : "The SMS could not be sent, so give the customer the ticket code."}{" "}
          <Link to={`/repairs/${done.id}`}>Open repair →</Link>
        </div>
      )}

      <form className="card stack" onSubmit={submit}>
        <div className="grid">
          <label>Customer name<input ref={nameRef} autoFocus value={f.name} onChange={set("name")} required /></label>
          <label>Phone number
            <input value={f.phone} onChange={set("phone")} placeholder="0712 345 678" inputMode="tel" required minLength={5} />
          </label>
        </div>
        {known && (
          <div className="msg ok" style={{ margin: 0 }}>
            {known.visits > 0 ? "Returning customer" : "Known customer"}: <strong>{known.name}</strong>{" "}
            <TierBadge tier={known.tier} points={known.points} />{" "}
            {known.visits > 0 ? `· ${known.visits} completed visit${known.visits === 1 ? "" : "s"} · ${known.points} points` : "· no completed visits yet"}
            {f.name.trim() && f.name.trim().toLowerCase() !== known.name.toLowerCase() && <div className="sub">Saved under the name "{known.name}"; the existing record is kept.</div>}
          </div>
        )}

        <div className="grid">
          <label>Brand<input value={f.brand} onChange={set("brand")} placeholder="Samsung" required /></label>
          <label>Model<input value={f.model} onChange={set("model")} placeholder="Galaxy A14" required /></label>
          <label>IMEI (optional)<input value={f.imei} onChange={set("imei")} inputMode="numeric" maxLength={40} /></label>
        </div>

        <fieldset className="choice">
          <legend>Which service? (tick all that apply)</legend>
          {SERVICE_TYPES.map((s) => (
            <label key={s} className={`pick small ${f.services.includes(s) ? "on" : ""}`}>
              <input type="checkbox" checked={f.services.includes(s)} onChange={() => toggleService(s)} />
              <span><strong>{s}</strong></span>
            </label>
          ))}
        </fieldset>

        <label>What's wrong? (optional)
          <textarea value={f.service_details} onChange={set("service_details")} maxLength={2000} placeholder="e.g. cracked screen, won't charge" />
        </label>

        <div className="grid">
          <label>Service charged (KES)
            <input type="number" min="0" step="1" inputMode="numeric" value={f.service_fee} onChange={set("service_fee")} placeholder="0" />
          </label>
          <label>Assigned technician (optional)
            <input list="staff-names" value={f.assigned_to} onChange={set("assigned_to")} />
          </label>
        </div>
        <StaffDatalist />

        <label className="check">
          <input type="checkbox" checked={f.needs_part} onChange={(e) => setF({ ...f, needs_part: e.target.checked })} />
          This phone needs a part
        </label>

        {f.needs_part && (
          <>
            <div className="grid">
              <label>Part needed
                <input value={f.part_name} onChange={set("part_name")} placeholder="e.g. A14 screen" required maxLength={120} />
              </label>
              <label>Where is it from?
                <select value={f.part_source} onChange={set("part_source")} required>
                  <option value="">Select…</option>
                  <option value="stock">In shop stock</option>
                  <option value="purchase">Must be bought</option>
                </select>
              </label>
              <label>Part cost to shop (KES)
                <input type="number" min="0" step="1" inputMode="numeric" value={f.part_cost} onChange={set("part_cost")} placeholder="0" />
              </label>
              <label>Part price to customer (KES)
                <input type="number" min="0" step="1" inputMode="numeric" value={f.part_price} onChange={set("part_price")} placeholder="same as cost" />
              </label>
            </div>
          </>
        )}

        <div className="muted">Total to charge: <strong>{money(total)}</strong> <span className="small">(payments are recorded later on the repair page)</span></div>

        <Notice n={error} />
        <div><button className="btn" disabled={busy}>{busy ? "Saving…" : "Register & notify customer"}</button></div>
      </form>
    </>
  );
}
