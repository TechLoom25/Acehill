import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Notice, PageHeader, Spinner } from "../components/ui.jsx";
import { fmt, methodLabel, money, todayShop } from "../lib.js";

const PERIODS = [
  ["today", "Today"],
  ["week", "This week"],
  ["last_week", "Last week"],
  ["month", "This month"],
  ["last_month", "Last month"],
  ["all", "All time"],
  ["custom", "Choose dates…"],
];

const JOB_SORTS = {
  newest: ["Date collected: newest first", (a, b) => b.collected_at.localeCompare(a.collected_at)],
  oldest: ["Date collected: oldest first", (a, b) => a.collected_at.localeCompare(b.collected_at)],
  profit: ["Profit: highest first", (a, b) => b.profit - a.profit],
  total: ["Total: highest first", (a, b) => b.total - a.total],
};

const day = (iso) => new Date(`${iso}T00:00:00`); // shop-local calendar date; only used for labels
const shortDay = (iso) => day(iso).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
const range = (a, b) => {
  const f = (iso) => day(iso).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
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
          <div className="chart-col" key={d.date} title={`${shortDay(d.date)}\nCash ${money(d.cash)}\nProfit ${money(d.profit)}`}>
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
  const [period, setPeriod] = useState("today"); // end-of-day first
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [start, setStart] = useState(() => todayShop(-6));
  const [end, setEnd] = useState(() => todayShop());
  const [jobSort, setJobSort] = useState("newest");
  const [dayOrder, setDayOrder] = useState("asc");

  const badRange = period === "custom" && (!start || !end || end < start);

  useEffect(() => {
    if (badRange) return undefined;
    let alive = true;
    setData(null);
    setError(null);
    const qs = period === "custom" ? `period=custom&start=${start}&end=${end}` : `period=${period}`;
    api(`/reports/finance?${qs}`)
      .then((d) => alive && setData(d))
      .catch((ex) => alive && setError({ type: "err", text: ex.message }));
    return () => { alive = false; };
  }, [period, start, end, badRange]);

  const jobs = useMemo(() => (data ? [...data.jobs].sort(JOB_SORTS[jobSort][1]) : []), [data, jobSort]);
  const days = useMemo(
    () => (data ? [...data.daily].sort((a, b) => (dayOrder === "asc" ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date))) : []),
    [data, dayOrder]
  );
  const methods = data ? Object.entries(data.by_method).sort((a, b) => b[1] - a[1]) : [];
  const maxMethod = Math.max(1, ...methods.map(([, v]) => v));
  const multiDay = data && data.daily.length > 1;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  return (
    <>
      <PageHeader title="Finance" subtitle={data ? range(data.start, data.end) : "Service charged, parts cost and profit"}>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
          {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </PageHeader>
      {period === "custom" && (
        <div className="filters">
          <label>From<input type="date" value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} /></label>
          <label>To<input type="date" value={end} min={start || undefined} max={todayShop()} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
      )}
      {badRange && <Notice n={{ type: "warn", text: "Choose a start date and an end date that is on or after it." }} />}
      <Notice n={error} />
      {!data && !error && !badRange && <Spinner />}

      {data && (
        <>
          {data.parts_without_cost > 0 && (
            <Notice n={{ type: "warn", text: `${plural(data.parts_without_cost, "part")} on jobs collected in this period ${data.parts_without_cost === 1 ? "has" : "have"} no cost entered, so parts cost is understated and profit overstated. Open those repairs and fill in the part costs.` }} />
          )}

          <div className="stats">
            <Kpi label="Service charged" value={money(data.service_income)} hint={`${plural(data.repairs_collected, "job")} collected · ${data.service_only_jobs} service only`} />
            <Kpi label="Parts cost" value={money(data.parts_cost)} hint={`${plural(data.jobs_with_parts, "job")} used parts · what the shop paid`} />
            <Kpi label="Parts used" value={data.parts_used} hint="items fitted on collected jobs" />
            <Kpi label="Parts charged to customers" value={money(data.parts_revenue)} />
            <Kpi label="Profit" value={money(data.profit)} tone={data.profit > 0 ? "good" : data.profit < 0 ? "bad" : ""} hint="service + parts charged − parts cost" />
            <Kpi label="Cash received" value={money(data.cash_received)} hint={plural(data.payments_count, "payment")} />
            <Kpi label="Still owed (all jobs)" value={money(data.outstanding)} tone={data.outstanding ? "bad" : ""} hint={`${plural(data.outstanding_count, "job")} with a balance`} />
          </div>

          <section className="card">
            <div className="row spread">
              <h2>Jobs collected</h2>
              <select value={jobSort} onChange={(e) => setJobSort(e.target.value)} aria-label="Sort jobs" style={{ width: "auto" }}>
                {Object.entries(JOB_SORTS).map(([v, [l]]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Ticket</th><th>Device</th><th>Customer</th><th>Collected</th><th className="right">Service</th><th className="right">Parts cost</th><th className="right">Parts charged</th><th className="right">Total</th><th className="right">Profit</th></tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.repair_id}>
                      <td><Link to={`/repairs/${j.repair_id}`}><span className="badge">{j.ticket_code}</span></Link></td>
                      <td>{j.device}{j.incomplete && <span className="sub"> · could not complete</span>}{!j.had_parts && <span className="sub"> · service only</span>}</td>
                      <td>{j.customer}</td>
                      <td className="muted">{fmt(j.collected_at)}</td>
                      <td className="right">{money(j.service)}</td>
                      <td className="right">{money(j.parts_cost)}</td>
                      <td className="right">{money(j.parts_charged)}</td>
                      <td className="right">{money(j.total)}</td>
                      <td className="right"><strong>{money(j.profit)}</strong></td>
                    </tr>
                  ))}
                  {!data.jobs.length && <tr><td colSpan="9" className="muted">No jobs were collected in this period.</td></tr>}
                </tbody>
                {data.jobs.length > 0 && (
                  <tfoot>
                    <tr>
                      <td colSpan="4">Total</td>
                      <td className="right">{money(data.service_income)}</td>
                      <td className="right">{money(data.parts_cost)}</td>
                      <td className="right">{money(data.parts_revenue)}</td>
                      <td className="right">{money(data.revenue)}</td>
                      <td className="right">{money(data.profit)}</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </section>

          {data.daily_omitted && (
            <Notice n={{ type: "warn", text: "This range is too long for a day-by-day breakdown. Choose a shorter range to see it." }} />
          )}
          {multiDay && (
            <section className="card">
              <div className="row spread">
                <h2>Day by day</h2>
                <select value={dayOrder} onChange={(e) => setDayOrder(e.target.value)} aria-label="Order days" style={{ width: "auto" }}>
                  <option value="asc">Oldest first</option>
                  <option value="desc">Newest first</option>
                </select>
              </div>
              <DailyChart daily={data.daily} />
              <div className="table-wrap" style={{ marginTop: 16 }}>
                <table>
                  <thead><tr><th>Day</th><th className="right">Jobs</th><th className="right">Service charged</th><th className="right">Parts cost</th><th className="right">Profit</th><th className="right">Cash received</th></tr></thead>
                  <tbody>
                    {days.map((d) => (
                      <tr key={d.date}>
                        <td>{shortDay(d.date)}</td>
                        <td className="right">{d.jobs}</td>
                        <td className="right">{money(d.service)}</td>
                        <td className="right">{money(d.parts_cost)}</td>
                        <td className="right"><strong>{money(d.profit)}</strong></td>
                        <td className="right">{money(d.cash)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="card">
            <h2>Payments by method</h2>
            <div className="bars">
              {methods.map(([m, v]) => (
                <div className="bar-row" key={m} style={{ gridTemplateColumns: "90px 1fr 100px" }}>
                  <span>{methodLabel(m)}</span>
                  <div className="bar"><div style={{ width: `${(v / maxMethod) * 100}%` }} /></div>
                  <b>{money(v)}</b>
                </div>
              ))}
              {!methods.length && <p className="muted">No payments in this period.</p>}
            </div>
          </section>

          <p className="muted small">
            <strong>Service charged</strong>, <strong>parts cost</strong> and <strong>profit</strong> count jobs <em>collected</em> in the period.{" "}
            <strong>Cash received</strong> counts payments taken in the period, including deposits on jobs still in progress.
            Times are shown in shop time.
          </p>
        </>
      )}
    </>
  );
}
