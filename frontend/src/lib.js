export const STATUSES = [
  ["received", "Received"],
  ["diagnosing", "Diagnosing"],
  ["waiting_parts", "Waiting for parts"],
  ["repairing", "Repairing"],
  ["ready", "Ready for pickup"],
  ["collected", "Collected"],
];
export const statusLabel = (s) => STATUSES.find(([v]) => v === s)?.[1] ?? s;

export const ROLES = [
  ["admin", "Administrator"],
  ["manager", "Manager"],
  ["front_desk", "Front desk"],
  ["technician", "Technician"],
];
export const roleLabel = (r) => ROLES.find(([v]) => v === r)?.[1] ?? r;

/** Who may use each feature. Mirrors the backend; the API is the real gatekeeper. Admins always pass. */
export const ACCESS = {
  intake: ["manager", "front_desk"],
  money: ["manager", "front_desk"], // see prices, take payments, edit part costs
  sms: ["manager"],
  staff: [],
  finance: [],
};

export const PAYMENT_METHODS = [
  ["cash", "Cash"],
  ["mpesa", "M-Pesa"],
  ["card", "Card"],
  ["bank", "Bank transfer"],
  ["other", "Other"],
];
export const methodLabel = (m) => PAYMENT_METHODS.find(([v]) => v === m)?.[1] ?? m;

export const PART_SOURCES = [
  ["stock", "From shop stock"],
  ["purchase", "To be purchased"],
];

const kes = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", maximumFractionDigits: 0 });
export const money = (n) => kes.format(n ?? 0);
/** Form input -> whole shillings (never negative, never NaN). */
export const toAmount = (v) => Math.max(0, Math.round(Number(v) || 0));

export const SERVICE_TYPES = [
  "Screen replacement",
  "Battery replacement",
  "Charging port",
  "Software / flashing",
  "Water damage",
  "Other",
];

// API times are UTC; older rows may lack a "Z" suffix
export const toDate = (s) => new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
export const fmt = (d) => (d ? toDate(d).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");

export const toLocalInput = (s) => {
  if (!s) return "";
  const d = toDate(s);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

export function timeAgo(s) {
  if (!s) return "never";
  const secs = Math.round((Date.now() - toDate(s).getTime()) / 1000);
  if (secs < 60) return "just now";
  const units = [["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, size] of units) {
    if (secs >= size) {
      const n = Math.floor(secs / size);
      return `${n} ${name}${n > 1 ? "s" : ""} ago`;
    }
  }
}

export const initials = (name = "") =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

export const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};
