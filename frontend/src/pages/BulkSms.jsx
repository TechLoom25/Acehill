import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Notice, PageHeader, Spinner } from "../components/ui.jsx";

export default function BulkSms() {
  const [customers, setCustomers] = useState(null);
  const [mode, setMode] = useState("all");
  const [picked, setPicked] = useState({});
  const [filter, setFilter] = useState("");
  const [message, setMessage] = useState("");
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/customers").then(setCustomers).catch((e) => { setCustomers([]); setNote({ type: "err", text: e.message }); });
  }, []);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (customers ?? []).filter((c) => !q || c.name.toLowerCase().includes(q) || c.phone.includes(q));
  }, [customers, filter]);

  const recipients = mode === "all"
    ? (customers ?? []).map((c) => c.phone)
    : (customers ?? []).filter((c) => picked[c.id]).map((c) => c.phone);

  const toggleVisible = (on) =>
    setPicked((p) => ({ ...p, ...Object.fromEntries(visible.map((c) => [c.id, on])) }));

  async function send() {
    if (!window.confirm(`Send this SMS to ${recipients.length} customer(s)?`)) return;
    setBusy(true);
    setNote(null);
    try {
      const r = await api("/sms/bulk", { method: "POST", body: { message, phones: recipients } });
      setNote({ type: "ok", text: `Sent to ${r.sent_to} customer(s).` });
      setMessage("");
    } catch (ex) {
      setNote({ type: "err", text: ex.message });
    }
    setBusy(false);
  }

  if (customers === null) return <Spinner />;
  const parts = Math.max(1, Math.ceil(message.length / 160));

  return (
    <>
      <PageHeader title="Bulk SMS" subtitle="Send an announcement to all customers or a hand-picked group." />
      <div className="card stack">
        <div className="row" style={{ marginBottom: 0 }}>
          <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ width: "auto" }} aria-label="Recipients">
            <option value="all">All customers ({customers.length})</option>
            <option value="pick">Choose customers</option>
          </select>
          {mode === "pick" && <span className="muted">{recipients.length} selected</span>}
        </div>

        {mode === "pick" && (
          <div className="picker">
            <div className="row" style={{ marginBottom: 8 }}>
              <input type="search" placeholder="Filter by name or phone" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ flex: 1 }} />
              <button type="button" className="btn ghost sm" onClick={() => toggleVisible(true)}>Select shown</button>
              <button type="button" className="btn ghost sm" onClick={() => toggleVisible(false)}>Clear shown</button>
            </div>
            <div className="picker-list">
              {visible.map((c) => (
                <label key={c.id} className="check">
                  <input type="checkbox" checked={!!picked[c.id]} onChange={(e) => setPicked({ ...picked, [c.id]: e.target.checked })} />
                  {c.name} <span className="muted">· {c.phone}</span>
                </label>
              ))}
              {!visible.length && <p className="muted">No customers found.</p>}
            </div>
          </div>
        )}

        <label>Message
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={1000} />
          <span className="hint">{message.length} characters · {parts} SMS part{parts > 1 ? "s" : ""} per recipient</span>
        </label>
        <Notice n={note} />
        <div>
          <button className="btn" disabled={busy || !message.trim() || !recipients.length} onClick={send}>
            {busy ? "Sending…" : `Send to ${recipients.length}`}
          </button>
        </div>
      </div>
    </>
  );
}
