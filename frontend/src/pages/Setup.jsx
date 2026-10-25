import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { Notice } from "../components/ui.jsx";
import { useAuth } from "../auth.jsx";

export default function Setup() {
  const { setup, setupKeyRequired } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState({ full_name: "", username: "", password: "", confirm: "", setup_key: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    if (f.password !== f.confirm) return setError({ type: "err", text: "Passwords don't match." });
    setBusy(true);
    setError(null);
    try {
      const { confirm, ...body } = f;
      await setup(body);
      navigate("/", { replace: true });
    } catch (ex) {
      setError({ type: "err", text: ex.message });
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Set up Acehill Repair"
      subtitle="Create the administrator account. You can add the rest of your team afterwards."
      footer="This screen only appears once, until the first admin exists."
    >
      <form className="stack" onSubmit={submit}>
        <label>Your full name
          <input autoFocus value={f.full_name} onChange={set("full_name")} required maxLength={80} />
        </label>
        <label>Username
          <input autoComplete="username" value={f.username} onChange={set("username")} required
            pattern="[A-Za-z0-9._\-]{3,32}" title="3–32 letters, numbers, dots, dashes or underscores" />
        </label>
        <label>Password (min. 8 characters)
          <input type="password" autoComplete="new-password" value={f.password} onChange={set("password")} required minLength={8} />
        </label>
        <label>Confirm password
          <input type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} required minLength={8} />
        </label>
        {setupKeyRequired && (
          <label>Setup key
            <input type="password" value={f.setup_key} onChange={set("setup_key")} required />
            <span className="hint">The SETUP_KEY value from the server's .env file.</span>
          </label>
        )}
        <Notice n={error} />
        <button className="btn block" disabled={busy}>{busy ? "Creating…" : "Create admin & continue"}</button>
      </form>
    </AuthShell>
  );
}
