import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Notice, PageHeader, Spinner } from "../components/ui.jsx";
import { methodLabel, money } from "../lib.js";

const PERIODS = [
  ["today", "Today"],
  ["week", "This week"],
  ["last_week", "Last week"],
  ["month", "This month"],
  ["last_month", "Last month"],
];

const day = (iso) => new Date(`${iso}T00:00:00`);
const range = (a, b) => {
  const f = (iso) => day(iso).toLocaleDateString([], { day: "numeric", month: "short" });
  return a === b ? f(a) : `${f(a)} – ${f(b)}`;
};

function Kpi({ label, value, hint, tone }) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="sub">{hint}</span>}
    </div>
  );
}

function DailyChart({ daily }) {
  const max = Math.max(1, ...daily.flatMap((d) => [d.cash, d.profit]));
  const long = daily.length > 10;
  return (
    <>
      <div className="chart" role="img" aria-label="Cash received and profit per day">
        {daily.map((d) => (
          <div className="chart-col" key={d.date} title={`${day(d.date).toLocaleDateString([], { dateStyle: "medium" })}\nCash ${money(d.cash)}\nProfit ${money(d.profit)}`}>
            <div className="chart-bars">
              <div className="cash" style={{ height: `${(d.cash / max) * 100}%` }} />
              <div className="profit" style={{ height: `${(d.profit / max) * 100}%` }} />
            </div>
            <span>{long ? day(d.date).getDate() : day(d.date).toLocaleDateString([], { weekday: "short" })}</span>
          </div>
        ))}
      </div>
      <div className="legend"><span><i className="cash" />Cash received</span><span><i className="profit" />Profit</span></div>
    </>
  );
}

export default function Finance() {
  const [period, setPeriod] = useState("week");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api(`/reports/finance?period=${period}`)
      .then((d) => alive && setData(d))
      .catch((ex) => alive && setError({ type: "err", text: ex.message }));
    return () => { alive = false; };
  }, [period]);

  const methods = data ? Object.entries(data.by_method).sort((a, b) => b[1] - a[1]) : [];
  const maxMethod = Math.max(1, ...methods.map(([, v]) => v));

  return (
    <>
      <PageHeader title="Finance" subtitle={data ? range(data.start, data.end) : "Income, costs and profit"}>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
          {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </PageHeader>
      <Notice n={error} />
      {!data && !error && <Spinner />}

      {data && (
        <>
          {data.parts_without_cost > 0 && (
            <Notice n={{ type: "warn", text: `${data.parts_without_cost} part(s) on jobs collected in this period have no cost entered, so profit may be overstated. Open those repairs and fill in the part costs.` }} />
          )}

          <div className="stats">
            <Kpi label="Cash received" value={money(data.cash_received)} hint={`${data.payments_count} payment${data.payments_count === 1 ? "" : "s"}`} />
            <Kpi label="Profit" value={money(data.profit)} tone={data.profit > 0 ? "good" : data.profit < 0 ? "bad" : ""} hint={`${data.repairs_collected} job${data.repairs_collected === 1 ? "" : "s"} collected`} />
            <Kpi label="Billed on collected jobs" value={money(data.revenue)} />
            <Kpi label="Parts cost" value={money(data.parts_cost)} />
            <Kpi label="Still owed (all jobs)" value={money(data.outstanding)} tone={data.outstanding ? "bad" : ""} hint={`${data.outstanding_count} job${data.outstanding_count === 1 ? "" : "s"} with a balance`} />
          </div>

          <div className="split">
            <section className="card">
              <h2>Per day</h2>
              <DailyChart daily={data.daily} />
            </section>

            <section className="card">
              <h2>Where the profit comes from</h2>
              <table className="summary">
                <tbody>
                  <tr><td>Service fees</td><td className="right">{money(data.service_income)}</td></tr>
                  <tr><td>Parts charged to customers</td><td className="right">{money(data.parts_revenue)}</td></tr>
                  <tr><td>Parts cost to the shop</td><td className="right">− {money(data.parts_cost)}</td></tr>
                  <tr className="total"><td>Profit</td><td className="right">{money(data.profit)}</td></tr>
                </tbody>
              </table>

              <h2 style={{ marginTop: 22 }}>Payments by method</h2>
              <div className="bars">
                {methods.map(([m, v]) => (
                  <div className="bar-row" key={m} style={{ gridTemplateColumns: "90px 1fr 90px" }}>
                    <span>{methodLabel(m)}</span>
                    <div className="bar"><div style={{ width: `${(v / maxMethod) * 100}%` }} /></div>
                    <b>{money(v)}</b>
                  </div>
                ))}
                {!methods.length && <p className="muted">No payments in this period.</p>}
              </div>
            </section>
          </div>

          <p className="muted small">
            <strong>Cash received</strong> counts payments taken in the period, including deposits on jobs still in progress.{" "}
            <strong>Profit</strong> counts jobs <em>collected</em> in the period: service fee plus parts charged, minus what the parts cost the shop.
          </p>
        </>
      )}
    </>
  );
}
