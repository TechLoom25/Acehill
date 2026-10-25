import { useEffect, useRef } from "react";
import { statusLabel } from "../lib.js";

const ICONS = {
  dashboard: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M14 14h7v7h-7z", "M3 14h7v7H3z"],
  wrench: ["M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"],
  plus: ["M12 5v14", "M5 12h14"],
  message: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  users: ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2", "M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z", "M23 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
  search: ["M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0z", "M21 21l-4.35-4.35"],
  menu: ["M3 12h18", "M3 6h18", "M3 18h18"],
  close: ["M18 6L6 18", "M6 6l12 12"],
  chart: ["M18 20V10", "M12 20V4", "M6 20v-6"],
  track: ["M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11z", "M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
};

export function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {(ICONS[name] ?? []).map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

export function Notice({ n }) {
  return n ? <div className={`msg ${n.type}`} role={n.type === "err" ? "alert" : "status"}>{n.text}</div> : null;
}

export const StatusBadge = ({ status }) => <span className={`badge st-${status}`}>{statusLabel(status)}</span>;

export function ProgressBar({ value }) {
  const pct = Math.min(100, Math.max(0, Number(value) || 0));
  return <div className="bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${pct}%` }} /></div>;
}

export const Spinner = ({ label = "Loading…" }) => <div className="spinner" role="status"><span />{label}</div>;

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

/** Accessible modal built on the native <dialog> element (focus trap + Esc handled by the browser). */
export function Modal({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog.open) dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <div className="modal-body">
        <div className="modal-head">
          <h2 id="modal-title">{title}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><Icon name="close" /></button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
