import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Icon, Notice, PageHeader, ProgressBar, Spinner, TierBadge } from "../components/ui.jsx";
import StaffDatalist from "../components/StaffDatalist.jsx";
import { STATUSES, money, toLocalInput } from "../lib.js";

function RepairRow({ r, showMoney, onSaved, onError }) {
  const initial = {
    status: r.status,
    progress: r.progress,
    assigned_to: r.assigned_to || "",
    eta: toLocalInput(r.estimated_completion),
    reason: r.failure_reason || "",
  };
  const [d, setD] = useState(initial);
  const [busy, setBusy] = useState(false);
  const needsReason = d.status === "incomplete";
  const dirty =
    d.status !== initial.status || Number(d.progress) !== initial.progress ||
    d.assigned_to !== initial.assigned_to || d.eta !== initial.eta ||
    (needsReason && d.reason.trim() !== initial.reason);
  const canSave = dirty && (!needsReason || d.reason.trim().length > 0);

  const changeStatus = (status) =>
    setD({ ...d, status, progress: status === "ready" || status === "collected" ? 100 : d.progress });

  async function save() {
    setBusy(true);
    try {
      const saved = await api(`/repairs/${r.id}`, {
        method: "PATCH",
        body: {
          status: d.status,
          progress: Math.min(100, Math.max(0, Number(d.progress) || 0)),
          assigned_to: d.assigned_to,
          estimated_completion: d.eta ? new Date(d.eta).toISOString() : null,
          reason: needsReason ? d.reason.trim() : undefined,
        },
      });
      onSaved(saved);
    } catch (ex) {
      onError(ex.message);
      setBusy(false);
    }
  }

  return (
    <tr>
      <td><span className="badge">{r.ticket_code}</span></td>
      <td>
        <Link to={`/repairs/${r.id}`}><strong>{r.brand} {r.model}</strong></Link>
        <div className="sub">
          {r.customer_name} <TierBadge tier={r.customer_tier} points={r.customer_points} /> · {r.service_type}
        </div>
        <div className="sub">{r.customer_phone ? `${r.customer_phone} · ` : ""}IMEI {r.imei}</div>
      </td>
      {showMoney && (
        <td>
          {money(r.money.total)}
          <div className="sub">
            {r.money.balance > 0 ? <span className="owed">{money(r.money.balance)} due</span> : r.money.total > 0 ? "Paid" : "No price yet"}
          </div>
        </td>
      )}
      <td>
        <select value={d.status} onChange={(e) => changeStatus(e.target.value)} aria-label="Status">
          {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {needsReason && (
          <textarea
            className="reason"
            aria-label="Reason the repair could not be completed"
            placeholder="Why couldn't it be fully repaired? (required)"
            value={d.reason}
            maxLength={1000}
            onChange={(e) => setD({ ...d, reason: e.target.value })}
          />
        )}
      </td>
      <td style={{ minWidth: 120 }}>
        <input type="number" min="0" max="100" value={d.progress} aria-label="Progress percent"
          onChange={(e) => setD({ ...d, progress: e.target.value })} />
        <div style={{ marginTop: 6 }}><ProgressBar value={d.progress} /></div>
      </td>
      <td><input type="datetime-local" value={d.eta} aria-label="Ready by" onChange={(e) => setD({ ...d, eta: e.target.value })} /></td>
      <td><input list="staff-names" value={d.assigned_to} aria-label="Technician" onChange={(e) => setD({ ...d, assigned_to: e.target.value })} /></td>
      <td><button className="btn sm" disabled={!canSave || busy} onClick={save}>{busy ? "…" : "Save"}</button></td>
    </tr>
  );
}

export default function Repairs() {
  const { can } = useAuth();
  const showMoney = can("money");
  const [rows, setRows] = useState(null);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [note, setNote] = useState(useLocation().state?.flash ?? null);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (query.trim()) params.set("q", query.trim());
    try {
      setRows(await api(`/repairs?${params}`));
    } catch (ex) {
      setNote({ type: "err", text: ex.message });
    }
  }, [status, query]);

  // Debounce so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(load, query ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, query]);

  function saved(updated) {
    setRows((rs) => rs.map((r) => (r.id === updated.id ? updated : r)));
    const unpaid = updated.status === "collected" && updated.money?.balance > 0;
    setNote({
      type: unpaid ? "warn" : "ok",
      text: `Ticket ${updated.ticket_code} updated.` +
        (updated.sms_sent === true ? " Customer notified by SMS." : updated.sms_sent === false ? " The SMS could not be sent." : "") +
        (unpaid ? ` Collected with ${money(updated.money.balance)} still unpaid.` : ""),
    });
  }

  return (
    <>
      <PageHeader title="Repairs" subtitle="Update status and progress. Changing the status texts the customer.">
        {can("intake") && <Link to="/repairs/new" className="btn">+ New repair</Link>}
      </PageHeader>
      <section className="card">
        <div className="row">
          <div className="search">
            <Icon name="search" size={16} />
            <input type="search" placeholder="Search ticket, IMEI, device or customer" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: "auto" }} aria-label="Filter by status">
            <option value="">All statuses</option>
            {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="btn ghost" onClick={load}>Refresh</button>
        </div>
        <Notice n={note} />
        <StaffDatalist />
        {rows === null ? <Spinner /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Ticket</th><th>Device</th>{showMoney && <th>Charges</th>}<th>Status</th><th>Progress %</th><th>Ready by</th><th>Technician</th><th /></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <RepairRow key={`${r.id}-${r.updated_at}`} r={r} showMoney={showMoney} onSaved={saved} onError={(text) => setNote({ type: "err", text })} />
                ))}
                {!rows.length && <tr><td colSpan={showMoney ? 8 : 7} className="muted">No repairs match.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {rows && rows.length > 0 && <p className="muted small">Showing {rows.length} repair{rows.length > 1 ? "s" : ""}, newest first.</p>}
      </section>
    </>
  );
}
