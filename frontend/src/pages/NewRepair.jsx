import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Notice, PageHeader, TierBadge } from "../components/ui.jsx";
import StaffDatalist from "../components/StaffDatalist.jsx";

const empty = {
  phone: "", name: "", brand: "", model: "", imei: "", service_details: "", assigned_to: "",
  needs_part: false, part_name: "", part_source: "",
};

export default function NewRepair() {
  const [f, setF] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null); // the repair that was just registered
  const [known, setKnown] = useState(null); // saved customer matching the number typed
  const phoneRef = useRef(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  // Look the number up as it is typed and fill in the saved name.
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
    setBusy(true);
    setError(null);
    try {
      const body = { ...f, part_name: f.needs_part ? f.part_name : "", part_source: f.part_source || "purchase" };
      const r = await api("/repairs", { method: "POST", body });
      setDone(r);
      setF(empty);
      setKnown(null);
      phoneRef.current?.focus(); // ready for the next customer
    } catch (ex) {
      setError({ type: "err", text: ex.message });
    }
    setBusy(false);
  }

  return (
    <>
      <PageHeader title="Register a phone" subtitle="Quick check-in. Prices and payments are added later on the repair page.">
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
          <label>Customer's phone number
            <input ref={phoneRef} autoFocus value={f.phone} onChange={set("phone")} placeholder="0712 345 678" inputMode="tel" required minLength={5} />
          </label>
          <label>Customer name<input value={f.name} onChange={set("name")} required /></label>
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

        <label>What's wrong? (optional)
          <textarea value={f.service_details} onChange={set("service_details")} maxLength={2000} placeholder="e.g. cracked screen, won't charge" />
        </label>

        <fieldset className="choice">
          <legend>What does it need?</legend>
          <label className={`pick ${!f.needs_part ? "on" : ""}`}>
            <input type="radio" name="job" checked={!f.needs_part} onChange={() => setF({ ...f, needs_part: false })} />
            <span><strong>Service only</strong><small>No part needed</small></span>
          </label>
          <label className={`pick ${f.needs_part ? "on" : ""}`}>
            <input type="radio" name="job" checked={f.needs_part} onChange={() => setF({ ...f, needs_part: true })} />
            <span><strong>Needs a part</strong><small>Name it below</small></span>
          </label>
        </fieldset>

        {f.needs_part && (
          <div className="grid">
            <label>Part needed
              <input value={f.part_name} onChange={set("part_name")} placeholder="e.g. A14 screen" required={f.needs_part} maxLength={120} />
            </label>
            <label>Where is it from?
              <select value={f.part_source} onChange={set("part_source")} required={f.needs_part}>
                <option value="">Select…</option>
                <option value="stock">In shop stock</option>
                <option value="purchase">Must be bought</option>
              </select>
            </label>
          </div>
        )}

        <label>Assigned technician (optional)
          <input list="staff-names" value={f.assigned_to} onChange={set("assigned_to")} />
        </label>
        <StaffDatalist />

        <Notice n={error} />
        <div><button className="btn" disabled={busy}>{busy ? "Saving…" : "Register & notify customer"}</button></div>
      </form>
    </>
  );
}
