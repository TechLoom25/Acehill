import { useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Notice, PageHeader } from "../components/ui.jsx";
import { fmt, roleLabel } from "../lib.js";

export default function Account() {
  const { user } = useAuth();
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    if (f.new_password !== f.confirm) return setNote({ type: "err", text: "New passwords don't match." });
    setBusy(true);
    setNote(null);
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: f.current_password, new_password: f.new_password } });
      setNote({ type: "ok", text: "Password changed." });
      setF({ current_password: "", new_password: "", confirm: "" });
    } catch (ex) {
      setNote({ type: "err", text: ex.message });
    }
    setBusy(false);
  }

  return (
    <>
      <PageHeader title="My account" />
      <div className="split">
        <section className="card stack">
          <h2>Profile</h2>
          <dl className="facts">
            <dt>Name</dt><dd>{user.full_name}</dd>
            <dt>Username</dt><dd>{user.username}</dd>
            <dt>Role</dt><dd>{roleLabel(user.role)}</dd>
            <dt>Last sign-in</dt><dd>{fmt(user.last_login_at)}</dd>
          </dl>
        </section>
        <form className="card stack" onSubmit={submit}>
          <h2>Change password</h2>
          <label>Current password<input type="password" autoComplete="current-password" value={f.current_password} onChange={set("current_password")} required /></label>
          <label>New password (min. 8 characters)<input type="password" autoComplete="new-password" value={f.new_password} onChange={set("new_password")} required minLength={8} /></label>
          <label>Confirm new password<input type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} required minLength={8} /></label>
          <Notice n={note} />
          <div><button className="btn" disabled={busy}>{busy ? "Saving…" : "Update password"}</button></div>
        </form>
      </div>
    </>
  );
}
