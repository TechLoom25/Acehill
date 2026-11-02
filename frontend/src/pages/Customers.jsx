import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Icon, Notice, PageHeader, Spinner, TierBadge } from "../components/ui.jsx";
import { POINTS_HELP, fmtDay, money } from "../lib.js";

export default function Customers() {
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const [busyId, setBusyId] = useState(null);
  const [note, setNote] = useState(null);
  const [rows, setRows] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      api(`/customers?q=${encodeURIComponent(query.trim())}`)
        .then((d) => alive && (setRows(d), setError(null)))
        .catch((ex) => alive && setError({ type: "err", text: ex.message }));
    }, query ? 250 : 0);
    return () => { alive = false; clearTimeout(t); };
  }, [query]);

  async function remove(c) {
    const base = `Permanently delete customer ${c.name} (${c.phone})?`;
    if (!window.confirm(`${base}\n\nThis cannot be undone.`)) return;
    setBusyId(c.id);
    setNote(null);
    try {
      let r;
      try {
        r = await api(`/customers/${c.id}`, { method: "DELETE" });
      } catch (ex) {
        // The API refuses when the customer has repairs; offer the explicit, destructive option.
        if (ex.status !== 409) throw ex;
        const again = window.confirm(
          `${ex.message}\n\nDelete ${c.name} AND all of their repairs, parts and payments? ` +
          "This changes your finance reports and cannot be undone."
        );
        if (!again) return;
        r = await api(`/customers/${c.id}?delete_repairs=true`, { method: "DELETE" });
      }
      setRows((rs) => rs.filter((x) => x.id !== c.id));
      setNote({ type: "ok", text: `${c.name} deleted${r.repairs ? ` along with ${r.repairs} repair${r.repairs === 1 ? "" : "s"}` : ""}.` });
    } catch (ex) {
      setNote({ type: "err", text: ex.message });
    } finally {
      setBusyId(null);
    }
  }

  // Best customers first
  const sorted = rows && [...rows].sort((a, b) => b.points - a.points || a.name.localeCompare(b.name));

  return (
    <>
      <PageHeader title="Customers" subtitle="Everyone who has brought a device in, with their loyalty points." />
      <section className="card">
        <div className="row">
          <div className="search">
            <Icon name="search" size={16} />
            <input type="search" placeholder="Search by name or phone number" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          {rows && <span className="muted">{rows.length} customer{rows.length === 1 ? "" : "s"}</span>}
        </div>
        <p className="muted small" style={{ marginTop: 0 }}>{POINTS_HELP} Repairs marked "could not complete" don't earn points.</p>
        <Notice n={error} />
        <Notice n={note} />
        {!sorted && !error && <Spinner />}
        {sorted && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Customer</th><th>Phone</th><th>Level</th><th>Visits</th><th>Points</th><th>Total spent</th><th>Last visit</th>{isAdmin && <th />}</tr></thead>
              <tbody>
                {sorted.map((c) => (
                  <tr key={c.id}>
                    <td><strong>{c.name}</strong></td>
                    <td>{c.phone}</td>
                    <td><TierBadge tier={c.tier} points={c.points} showNew /></td>
                    <td>{c.visits}{c.repairs > c.visits && <span className="sub"> ({c.repairs} repairs)</span>}</td>
                    <td><strong>{c.points}</strong></td>
                    <td>{money(c.total_spent)}</td>
                    <td className="muted">{fmtDay(c.last_visit)}</td>
                    {isAdmin && (
                      <td><button className="btn danger sm" disabled={busyId === c.id} onClick={() => remove(c)} title="Delete this customer">Delete</button></td>
                    )}
                  </tr>
                ))}
                {!sorted.length && <tr><td colSpan={isAdmin ? 8 : 7} className="muted">No customers match.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
