const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "acehill.token";

export const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

let onUnauthorized = () => {};
/** Called when an authenticated request comes back 401 (expired or revoked session). */
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn;
};

// FastAPI returns either a string or a list of {loc, msg} for validation errors.
function formatDetail(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(" ") : "";
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return fallback;
}

export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw Object.assign(new Error("Cannot reach the server. Check that the backend is running."), { status: 0 });
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = formatDetail((await res.json()).detail, detail);
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && auth && token) {
      clearToken();
      onUnauthorized();
    }
    throw Object.assign(new Error(detail || "Request failed"), { status: res.status });
  }
  return res.json();
}
