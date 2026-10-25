import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { Notice } from "../components/ui.jsx";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const from = useLocation().state?.from || "/";
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(form.username, form.password);
      navigate(from, { replace: true });
    } catch (ex) {
      setError({ type: "err", text: ex.message });
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to the repair desk.">
      <form className="stack" onSubmit={submit}>
        <label>Username
          <input autoFocus autoComplete="username" value={form.username} required
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </label>
        <label>Password
          <input type="password" autoComplete="current-password" value={form.password} required
            onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        <Notice n={error} />
        <button className="btn block" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </AuthShell>
  );
}
