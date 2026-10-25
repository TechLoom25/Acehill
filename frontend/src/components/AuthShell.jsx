import { Link } from "react-router-dom";

/** Split-screen frame shared by the login and first-run setup screens. */
export default function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="auth">
      <section className="auth-hero">
        <span className="brand-mark lg">A</span>
        <h2>Acehill Repair</h2>
        <p>Intake, repair tracking and customer SMS, in one place.</p>
        <ul>
          <li>Every repair has a ticket and a live status</li>
          <li>Customers are texted automatically at each step</li>
          <li>Separate access for admins, managers, front desk and technicians</li>
        </ul>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <h1>{title}</h1>
          <p className="muted">{subtitle}</p>
          {children}
          <div className="auth-foot">{footer ?? <Link to="/track">Track a repair as a customer →</Link>}</div>
        </div>
      </section>
    </div>
  );
}
