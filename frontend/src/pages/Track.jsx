import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Notice, ProgressBar, StatusBadge } from "../components/ui.jsx";
import { fmt } from "../lib.js";

/** Public page: customers check a repair by ticket code. No sign-in, no personal data. */
export default function Track() {
  const { user } = useAuth();
  const [code, setCode] = useState("");
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function lookup(e) {
    e.preventDefault();
    setErr(null);
    setRes(null);
    setBusy(true);
    try {
      setRes(await api(`/track/${encodeURIComponent(code.trim())}`, { auth: false }));
    } catch (ex) {
      setErr({ type: "err", text: ex.status === 404 ? "We couldn't find that ticket. Check the code in your SMS." : ex.message });
    }
    setBusy(false);
  }

  return (
    <div className="track">
      <header className="track-bar">
        <span className="brand"><span className="brand-mark">A</span><strong>Acehill Repair</strong></span>
        <Link to={user ? "/" : "/login"}>{user ? "Back to dashboard" : "Staff sign in"}</Link>
      </header>
      <div className="card stack track-card">
        <h1>Track your repair</h1>
        <p className="muted">Enter the ticket code from your SMS.</p>
        <form className="row" onSubmit={lookup} style={{ marginBottom: 0 }}>
          <input style={{ flex: 1 }} placeholder="e.g. A1B2C3" value={code} onChange={(e) => setCode(e.target.value)} required maxLength={20} autoFocus />
          <button className="btn" disabled={busy}>{busy ? "Checking…" : "Check"}</button>
        </form>
        <Notice n={err} />
        {res && (
          <div className="stack result">
            <div className="row spread"><strong>{res.device}</strong><StatusBadge status={res.status} /></div>
            <ProgressBar value={res.progress} />
            <div className="row spread"><span>{res.progress}% complete</span><span className="muted">Ticket {res.ticket_code}</span></div>
            <div className="muted">Estimated ready: {fmt(res.estimated_completion)}</div>
            <div className="muted small">Last updated {fmt(res.updated_at)}</div>
          </div>
        )}
      </div>
    </div>
  );
}
