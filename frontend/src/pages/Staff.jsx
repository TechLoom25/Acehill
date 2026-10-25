import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Modal, Notice, PageHeader, Spinner } from "../components/ui.jsx";
import { ROLES, roleLabel, timeAgo } from "../lib.js";

function StaffForm({ person, onClose, onSaved }) {
  const { user: me } = useAuth();
  const editing = !!person;
  const isSelf = editing && person.id === me.id;
  const [f, setF] = useState({
    username: "", full_name: person?.full_name ?? "", role: person?.role ?? "technician",
    is_active: person?.is_active ?? true, password: "",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (editing) {
        const body = { full_name: f.full_name };
        if (!isSelf) { body.role = f.role; body.is_active = f.is_active; }
        if (f.password) body.password = f.password;
        await api(`/users/${person.id}`, { method: "PATCH", body });
      } else {
        await api("/users", { method: "POST", body: { username: f.username, full_name: f.full_name, role: f.role, password: f.password } });
      }
      onSaved(editing ? `${f.full_name} updated.` : `${f.full_name} can now sign in as ${f.username.toLowerCase()}.`);
    } catch (ex) {
      setError({ type: "err", text: ex.message });
      setBusy(false);
    }
  }

  return (
    <Modal title={editing ? `Edit ${person.full_name}` : "Add staff member"} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        {!editing && (
          <label>Username
            <input value={f.username} onChange={set("username")} required autoFocus autoComplete="off"
              pattern="[A-Za-z0-9._\-]{3,32}" title="3–32 letters, numbers, dots, dashes or underscores" />
          </label>
        )}
        <label>Full name<input value={f.full_name} onChange={set("full_name")} required maxLength={80} /></label>
        <label>Role
          <select value={f.role} onChange={set("role")} disabled={isSelf}>
            {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        {editing && (
          <label className="check">
            <input type="checkbox" checked={f.is_active} disabled={isSelf} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />
            Account is active
          </label>
        )}
        {isSelf && <p className="hint">You can't change your own role or disable your own account.</p>}
        <label>{editing ? "Reset password (leave blank to keep)" : "Password (min. 8 characters)"}
          <input type="password" autoComplete="new-password" value={f.password} onChange={set("password")} minLength={8} required={!editing} />
        </label>
        <Notice n={error} />
        <div className="row end">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Staff() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [dialog, setDialog] = useState(null); // null | "new" | user object
  const [note, setNote] = useState(null);

  const load = () => api("/users").then(setUsers).catch((ex) => setNote({ type: "err", text: ex.message }));
  useEffect(() => { load(); }, []);

  function saved(text) {
    setDialog(null);
    setNote({ type: "ok", text });
    load();
  }

  return (
    <>
      <PageHeader title="Staff" subtitle="Everyone who can sign in to Acehill Repair.">
        <button className="btn" onClick={() => setDialog("new")}>+ Add staff</button>
      </PageHeader>
      <Notice n={note} />
      <section className="card">
        {users === null ? <Spinner /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.full_name}</strong>{u.id === me.id && <span className="sub"> (you)</span>}</td>
                    <td>{u.username}</td>
                    <td><span className="badge">{roleLabel(u.role)}</span></td>
                    <td><span className={`badge ${u.is_active ? "st-ready" : "st-off"}`}>{u.is_active ? "Active" : "Disabled"}</span></td>
                    <td className="muted">{timeAgo(u.last_login_at)}</td>
                    <td><button className="btn ghost sm" onClick={() => setDialog(u)}>Edit</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>What each role can do</h2>
        <div className="table-wrap">
          <table className="matrix">
            <thead><tr><th /><th>Admin</th><th>Manager</th><th>Front desk</th><th>Technician</th></tr></thead>
            <tbody>
              {[
                ["View dashboard & repairs", 1, 1, 1, 1],
                ["Update repair status", 1, 1, 1, 1],
                ["Register new repairs", 1, 1, 1, 0],
                ["Bulk SMS", 1, 1, 0, 0],
                ["Manage staff accounts", 1, 0, 0, 0],
              ].map(([label, ...marks]) => (
                <tr key={label}><td>{label}</td>{marks.map((m, i) => <td key={i} aria-label={m ? "Yes" : "No"}>{m ? "✓" : "—"}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {dialog && <StaffForm person={dialog === "new" ? null : dialog} onClose={() => setDialog(null)} onSaved={saved} />}
    </>
  );
}
