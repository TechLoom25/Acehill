import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Icon, Notice, PageHeader, Spinner, TierBadge } from "../components/ui.jsx";
import { POINTS_HELP, money } from "../lib.js";

const day = (d) => (d ? new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(d) ? d : d + "Z").toLocaleDateString([], { dateStyle: "medium" }) : "—");

export default function Customers() {
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
        {!sorted && !error && <Spinner />}
        {sorted && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Customer</th><th>Phone</th><th>Level</th><th>Visits</th><th>Points</th><th>Total spent</th><th>Last visit</th></tr></thead>
              <tbody>
                {sorted.map((c) => (
                  <tr key={c.id}>
                    <td><strong>{c.name}</strong></td>
                    <td>{c.phone}</td>
                    <td><TierBadge tier={c.tier} points={c.points} showNew /></td>
                    <td>{c.visits}{c.repairs > c.visits && <span className="sub"> ({c.repairs} repairs)</span>}</td>
                    <td><strong>{c.points}</strong></td>
                    <td>{money(c.total_spent)}</td>
                    <td className="muted">{day(c.last_visit)}</td>
                  </tr>
                ))}
                {!sorted.length && <tr><td colSpan="7" className="muted">No customers match.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
