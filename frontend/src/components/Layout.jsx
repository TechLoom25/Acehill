import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { initials, roleLabel } from "../lib.js";
import { Icon } from "./ui.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: "dashboard", active: (p) => p === "/" },
  { to: "/repairs", label: "Repairs", icon: "wrench", active: (p) => p.startsWith("/repairs") && p !== "/repairs/new" },
  { to: "/repairs/new", label: "New repair", icon: "plus", access: "intake", active: (p) => p === "/repairs/new" },
  { to: "/customers", label: "Customers", icon: "star", access: "money", active: (p) => p.startsWith("/customers") },
  { to: "/finance", label: "Finance", icon: "chart", access: "finance", active: (p) => p.startsWith("/finance") },
  { to: "/sms", label: "Bulk SMS", icon: "message", access: "sms", active: (p) => p.startsWith("/sms") },
  { to: "/staff", label: "Staff", icon: "users", access: "staff", active: (p) => p.startsWith("/staff") },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">A</span>
          <div><strong>Acehill</strong><small>Repair desk</small></div>
        </div>

        <nav aria-label="Main">
          {NAV.filter((i) => !i.access || can(i.access)).map((i) => {
            const active = i.active(pathname);
            return (
              <Link key={i.to} to={i.to} className={`nav-link ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}>
                <Icon name={i.icon} />{i.label}
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <Link to="/track" className="nav-link"><Icon name="track" />Customer tracking</Link>
          <Link to="/account" className="user-chip">
            <span className="avatar">{initials(user.full_name)}</span>
            <span><strong>{user.full_name}</strong><small>{roleLabel(user.role)}</small></span>
          </Link>
          <button className="nav-link" onClick={logout}><Icon name="logout" />Sign out</button>
        </div>
      </aside>

      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <div className="content">
        <header className="topbar">
          <button className="icon-btn" aria-label="Open menu" onClick={() => setOpen(true)}><Icon name="menu" /></button>
          <strong>Acehill Repair</strong>
        </header>
        <main className="page"><Outlet /></main>
      </div>
    </div>
  );
}
