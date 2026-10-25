import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Notice, PageHeader, ProgressBar, Spinner, StatusBadge } from "../components/ui.jsx";
import { PAYMENT_METHODS, PART_SOURCES, fmt, methodLabel, money, toAmount } from "../lib.js";

const emptyPart = { name: "", quantity: 1, source: "stock", unit_cost: "", unit_price: "" };

function PartRow({ part, showMoney, locked, run }) {
  const [d, setD] = useState({ unit_cost: part.unit_cost ?? "", unit_price: part.unit_price ?? "" });
  const costChanged = showMoney && toAmount(d.unit_cost) !== part.unit_cost;
  const priceChanged = showMoney && toAmount(d.unit_price) !== part.unit_price;

  // Only send what changed: editing just the cost lets the server keep a no-markup price in step.
  const savePrices = () => {
    const body = {};
    if (costChanged) body.unit_cost = toAmount(d.unit_cost);
    if (priceChanged) body.unit_price = toAmount(d.unit_price);
    return run(() => api(`/parts/${part.id}`, { method: "PATCH", body }));
  };

  return (
    <tr>
      <td><strong>{part.name}</strong><div className="sub">added by {part.added_by || "—"}</div></td>
      <td>{part.quantity}</td>
      <td>
        <span className={`badge ${part.source === "purchase" ? "st-waiting_parts" : "st-received"}`}>
          {part.source === "purchase" ? "Purchase" : "Shop stock"}
        </span>
      </td>
      <td>
        {part.acquired ? (
          <span className="badge st-ready">{part.source === "purchase" ? "Bought" : "In shop"}</span>
        ) : (
          <button className="btn sm" disabled={locked}
            onClick={() => run(() => api(`/parts/${part.id}`, { method: "PATCH", body: { acquired: true } }))}>
            Mark bought
          </button>
        )}
      </td>
      {showMoney && (
        <>
          <td><input type="number" min="0" aria-label="Unit cost" value={d.unit_cost} disabled={locked} onChange={(e) => setD({ ...d, unit_cost: e.target.value })} /></td>
          <td><input type="number" min="0" aria-label="Unit price" value={d.unit_price} disabled={locked} onChange={(e) => setD({ ...d, unit_price: e.target.value })} /></td>
          <td>{money(part.unit_price * part.quantity)}</td>
        </>
      )}
      <td><div className="actions">
        {(costChanged || priceChanged) && <button className="btn sm" onClick={savePrices}>Save</button>}
        <button className="btn ghost sm" disabled={locked} onClick={() => window.confirm(`Remove ${part.name}?`) && run(() => api(`/parts/${part.id}`, { method: "DELETE" }))}>
          Remove
        </button>
      </div></td>
    </tr>
  );
}

export default function RepairDetail() {
  const { id } = useParams();
  const { user, can } = useAuth();
  const showMoney = can("money");
  const isAdmin = user.role === "admin";
  const [repair, setRepair] = useState(null);
  const [note, setNote] = useState(useLocation().state?.flash ?? null);
  const [missing, setMissing] = useState(false);
  const [part, setPart] = useState(emptyPart);
  const [pay, setPay] = useState({ amount: "", method: "cash", reference: "" });
  const [fee, setFee] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api(`/repairs/${id}`);
      setRepair(r);
      setFee(String(r.money?.service_fee ?? ""));
    } catch (ex) {
      if (ex.status === 404) setMissing(true);
      else setNote({ type: "err", text: ex.message });
    }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  /** Run a mutation, then refresh the whole job so every total stays consistent. */
  const run = async (action, success) => {
    setBusy(true);
    setNote(null);
    try {
      await action();
      await load();
      if (success) setNote({ type: "ok", text: success });
      return true;
    } catch (ex) {
      setNote({ type: "err", text: ex.message });
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (missing) return <><PageHeader title="Repair not found" /><Link to="/repairs">← Back to repairs</Link></>;
  if (!repair) return <>{<Notice n={note} />}<Spinner /></>;

  const m = repair.money;
  const locked = repair.status === "collected" && !isAdmin;

  async function addPart(e) {
    e.preventDefault();
    const body = { name: part.name, quantity: Number(part.quantity) || 1, source: part.source };
    if (showMoney && part.unit_cost !== "") body.unit_cost = toAmount(part.unit_cost);
    if (showMoney && part.unit_price !== "") body.unit_price = toAmount(part.unit_price);
    if (await run(() => api(`/repairs/${id}/parts`, { method: "POST", body }), `${part.name} added.`)) setPart(emptyPart);
  }

  async function addPayment(e) {
    e.preventDefault();
    const body = { amount: toAmount(pay.amount), method: pay.method, reference: pay.reference };
    if (await run(() => api(`/repairs/${id}/payments`, { method: "POST", body }), `Payment of ${money(body.amount)} recorded.`)) {
      setPay({ amount: "", method: "cash", reference: "" });
    }
  }

  return (
    <>
      <PageHeader title={`${repair.brand} ${repair.model}`} subtitle={`${repair.customer_name} · ${repair.service_type} · IMEI ${repair.imei}`}>
        <Link to="/repairs" className="btn ghost">← All repairs</Link>
      </PageHeader>
      <Notice n={note} />
      {locked && <Notice n={{ type: "warn", text: "This repair has been collected, so its parts and price are locked. An administrator can still change them." }} />}

      <div className="card">
        <div className="row spread" style={{ marginBottom: 8 }}>
          <span><span className="badge">{repair.ticket_code}</span> &nbsp;<StatusBadge status={repair.status} /></span>
          <span className="muted small">Registered {fmt(repair.created_at)} · Technician: {repair.assigned_to || "unassigned"}</span>
        </div>
        <ProgressBar value={repair.progress} />
        {repair.service_details && <p className="muted" style={{ marginBottom: 0 }}>{repair.service_details}</p>}
      </div>

      <div className="split">
        <section className="card">
          <h2>Parts needed</h2>
          <form className="parts-form" onSubmit={addPart}>
            <label className="grow">Part
              <input value={part.name} onChange={(e) => setPart({ ...part, name: e.target.value })} placeholder="e.g. A14 screen" required maxLength={120} disabled={locked} />
            </label>
            <label className="narrow">Qty
              <input type="number" min="1" value={part.quantity} onChange={(e) => setPart({ ...part, quantity: e.target.value })} disabled={locked} />
            </label>
            <label>Source
              <select value={part.source} onChange={(e) => setPart({ ...part, source: e.target.value })} disabled={locked}>
                {PART_SOURCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            {showMoney && (
              <>
                <label className="narrow">Cost<input type="number" min="0" value={part.unit_cost} onChange={(e) => setPart({ ...part, unit_cost: e.target.value })} placeholder="0" disabled={locked} /></label>
                <label className="narrow">Price<input type="number" min="0" value={part.unit_price} onChange={(e) => setPart({ ...part, unit_price: e.target.value })} placeholder="= cost" disabled={locked} /></label>
              </>
            )}
            <button className="btn" disabled={busy || locked}>Add part</button>
          </form>
          {showMoney && <p className="hint">Cost is what the part costs the shop; price is what the customer pays. Leave price empty to charge the same as the cost.</p>}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Part</th><th>Qty</th><th>Source</th><th>Status</th>
                  {showMoney && <><th>Cost (each)</th><th>Price (each)</th><th>Line total</th></>}
                  <th />
                </tr>
              </thead>
              <tbody>
                {repair.parts.map((p) => (
                  <PartRow key={`${p.id}-${p.unit_cost}-${p.unit_price}-${p.acquired}`} part={p} showMoney={showMoney} locked={locked} run={run} />
                ))}
                {!repair.parts.length && <tr><td colSpan={showMoney ? 8 : 5} className="muted">No parts listed yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {showMoney && (
          <div>
            <section className="card">
              <h2>Price summary</h2>
              <table className="summary">
                <tbody>
                  <tr>
                    <td>Service fee</td>
                    <td className="right">
                      <span className="inline-edit">
                        <input type="number" min="0" aria-label="Service fee" value={fee} disabled={locked} onChange={(e) => setFee(e.target.value)} />
                        {toAmount(fee) !== m.service_fee && (
                          <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/repairs/${id}`, { method: "PATCH", body: { service_fee: toAmount(fee), notify: false } }), "Service fee updated.")}>Save</button>
                        )}
                      </span>
                    </td>
                  </tr>
                  <tr><td>Parts</td><td className="right">{money(m.parts_total)}</td></tr>
                  <tr className="total"><td>Total</td><td className="right">{money(m.total)}</td></tr>
                  <tr><td>Paid</td><td className="right">{money(m.paid)}</td></tr>
                  <tr className={m.balance > 0 ? "owed-row" : ""}><td>{m.balance < 0 ? "Overpaid" : "Balance due"}</td><td className="right"><strong>{money(Math.abs(m.balance))}</strong></td></tr>
                  {isAdmin && (
                    <>
                      <tr className="admin-row"><td>Parts cost (shop)</td><td className="right">{money(m.parts_cost)}</td></tr>
                      <tr className="admin-row"><td>Profit on this job</td><td className="right"><strong>{money(m.profit)}</strong></td></tr>
                    </>
                  )}
                </tbody>
              </table>
            </section>

            <section className="card">
              <h2>Payments</h2>
              <form className="stack" onSubmit={addPayment}>
                <div className="grid">
                  <label>Amount (KES)
                    <input type="number" min="1" required value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} />
                  </label>
                  <label>Method
                    <select value={pay.method} onChange={(e) => setPay({ ...pay, method: e.target.value })}>
                      {PAYMENT_METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </label>
                </div>
                <label>Reference (optional)
                  <input value={pay.reference} maxLength={60} placeholder="e.g. M-Pesa code" onChange={(e) => setPay({ ...pay, reference: e.target.value })} />
                </label>
                <div className="row" style={{ marginBottom: 0 }}>
                  <button className="btn" disabled={busy}>Record payment</button>
                  {m.balance > 0 && <button type="button" className="btn ghost" onClick={() => setPay({ ...pay, amount: String(m.balance) })}>Fill balance ({money(m.balance)})</button>}
                </div>
              </form>
              <ul className="payments">
                {repair.payments.map((p) => (
                  <li key={p.id}>
                    <div>
                      <strong>{money(p.amount)}</strong> · {methodLabel(p.method)}
                      <div className="sub">{fmt(p.created_at)} · {p.received_by}{p.reference ? ` · ${p.reference}` : ""}</div>
                    </div>
                    {isAdmin && (
                      <button className="btn ghost sm" onClick={() => window.confirm("Delete this payment record?") && run(() => api(`/payments/${p.id}`, { method: "DELETE" }), "Payment deleted.")}>Delete</button>
                    )}
                  </li>
                ))}
                {!repair.payments.length && <li className="muted">No payments yet.</li>}
              </ul>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
