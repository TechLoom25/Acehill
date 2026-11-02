import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { PageHeader, ProgressBar, Notice, Spinner, StatusBadge } from "../components/ui.jsx";
import { STATUSES, fmt, greeting, money, timeAgo } from "../lib.js";

function Stat({ label, value, tone, to }) {
  const body = (<><span className="stat-label">{label}</span><span className="stat-value">{value}</span></>);
  return to ? <Link to={to} className={`stat ${tone ?? ""}`}>{body}</Link> : <div className={`stat ${tone ?? ""}`}>{body}</div>;
}

export default function Dashboard() {
  const { user, can } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null); // admin-only money summary
  const [period, setPeriod] = useState("today");
  const canFinance = can("finance");

  useEffect(() => {
    if (!canFinance) return undefined;
    let alive = true;
    setSummary(null);
    api(`/reports/finance?period=${period}`).then((d) => alive && setSummary(d)).catch(() => {});
    return () => { alive = false; };
  }, [canFinance, period]);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api("/dashboard")
        .then((d) => alive && (setData(d), setError(null)))
        .catch((ex) => alive && setError({ type: "err", text: ex.message }));
    load();
    const timer = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  const firstName = user.full_name.split(" ")[0];
  const header = (
    <PageHeader title={`${greeting()}, ${firstName}`} subtitle="Here's what's happening in the shop.">
      {can("intake") && <Link to="/repairs/new" className="btn">+ New repair</Link>}
    </PageHeader>
  );
  if (!data) return <>{header}<Notice n={error} />{!error && <Spinner />}</>;

  const maxStatus = Math.max(1, ...Object.values(data.by_status));
  const maxLoad = Math.max(1, ...data.workload.map((w) => w.open));

  return (
    <>
      {header}
      <Notice n={error} />
      <div className="stats">
        <Stat label="Open repairs" value={data.open} to="/repairs" />
        <Stat label="Ready for pickup" value={data.ready} tone="good" to="/repairs" />
        {data.incomplete > 0 && <Stat label="Could not complete" value={data.incomplete} tone="bad" to="/repairs" />}
        <Stat label="Overdue" value={data.overdue} tone={data.overdue ? "bad" : ""} to="/repairs" />
        <Stat label="New this week" value={data.new_this_week} />
        <Stat label="Finished this week" value={data.completed_this_week} />
        {can("sms") && <Stat label="Customers" value={data.customers} />}
      </div>

      {canFinance && (
        <section className="card">
          <div className="row spread">
            <h2>Money</h2>
            <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Money period" style={{ width: "auto" }}>
              <option value="today">Today</option>
              <option value="week">This week</option>
              <option value="month">This month</option>
              <option value="all">All time</option>
            </select>
          </div>
          {!summary ? <Spinner /> : (
            <div className="stats">
              <Stat label="Cost of parts used" value={money(summary.parts_cost)} to="/finance" />
              <Stat label="Parts used" value={summary.parts_used} to="/finance" />
              <Stat label="Total cash" value={money(summary.cash_received)} to="/finance" />
              <Stat label="Total profit" value={money(summary.profit)} tone={summary.profit > 0 ? "good" : summary.profit < 0 ? "bad" : ""} to="/finance" />
            </div>
          )}
        </section>
      )}

      <div className="split">
        <section className="card">
          <h2>Repairs by status</h2>
          <div className="bars">
            {STATUSES.map(([key, label]) => (
              <div className="bar-row" key={key}>
                <span>{label}</span>
                <div className="bar"><div style={{ width: `${(data.by_status[key] / maxStatus) * 100}%` }} /></div>
                <b>{data.by_status[key]}</b>
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <h2>Open work by technician</h2>
          {data.workload.length === 0 && <p className="muted">Nothing in progress.</p>}
          <div className="bars">
            {data.workload.map((w) => (
              <div className="bar-row" key={w.name}>
                <span>{w.name}</span>
                <div className="bar"><div style={{ width: `${(w.open / maxLoad) * 100}%` }} /></div>
                <b>{w.open}</b>
              </div>
            ))}
          </div>
        </section>
      </div>

      {data.parts_to_buy_count > 0 && (
        <section className="card">
          <h2>Parts to buy ({data.parts_to_buy_count})</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Part</th><th>Qty</th><th>For</th></tr></thead>
              <tbody>
                {data.parts_to_buy.map((p) => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong></td>
                    <td>{p.quantity}</td>
                    <td><Link to={`/repairs/${p.repair_id}`}>{p.device}</Link> <span className="badge">{p.ticket_code}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card">
        <div className="row spread"><h2>Recent repairs</h2><Link to="/repairs">View all →</Link></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Ticket</th><th>Customer</th><th>Device</th><th>Status</th><th>Progress</th><th>Updated</th></tr></thead>
            <tbody>
              {data.recent.map((r) => (
                <tr key={r.id}>
                  <td><span className="badge">{r.ticket_code}</span></td>
                  <td>{r.customer_name}</td>
                  <td>{r.brand} {r.model}</td>
                  <td><StatusBadge status={r.status} /></td>
                  <td style={{ minWidth: 110 }}><ProgressBar value={r.progress} /></td>
                  <td className="muted" title={fmt(r.updated_at)}>{timeAgo(r.updated_at)}</td>
                </tr>
              ))}
              {!data.recent.length && <tr><td colSpan="6" className="muted">No repairs yet. Register the first one!</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
