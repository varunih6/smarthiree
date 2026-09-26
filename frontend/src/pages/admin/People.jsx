import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { Badge, Card, Empty, ErrorBox, Field, Modal, PasswordInput, Spinner, StatusBadge, fmtDate, fmtDateTime, useFetch } from "../../components/ui";
import { useToast } from "../../context";

/* ------------------------------------------------------------------ interviewers (admin manages) */
export function Interviewers() {
  const toast = useToast();
  const { data, loading, error, reload } = useFetch(() => api.get("/admin/interviewers"));
  const [edit, setEdit] = useState(null); // {} for new

  const toggle = async (u) => {
    try { await api.patch(`/admin/interviewers/${u.id}`, { is_active: !u.is_active }); toast.success(u.is_active ? "Deactivated" : "Activated"); reload(true); }
    catch (e) { toast.error(e.message); }
  };
  const remove = async (u) => {
    if (!window.confirm(`Remove ${u.full_name}?`)) return;
    try { const r = await api.del(`/admin/interviewers/${u.id}`); toast.info(r.message); reload(true); } catch (e) { toast.error(e.message); }
  };

  return (
    <>
      <PageHead title="Interviewers" sub="Interviewers cannot self-register — create their login credentials here and share them.">
        <button className="btn btn-primary" onClick={() => setEdit({})}>+ Add interviewer</button>
      </PageHead>
      <ErrorBox error={error} />
      {loading ? <Spinner /> : (
        <Card>
          {data.length === 0 ? <Empty title="No interviewers yet" /> : (
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Name</th><th>Email</th><th>Designation</th><th>Assigned</th><th>Free slots</th><th>Status</th><th /></tr></thead>
              <tbody>
                {data.map((u) => (
                  <tr key={u.id}>
                    <td><b>{u.full_name}</b></td><td>{u.email}</td><td>{u.designation || "—"}</td>
                    <td>{u.assigned}</td><td>{u.free_slots}</td>
                    <td>{u.is_active ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>}</td>
                    <td className="nowrap">
                      <button className="btn btn-xs" onClick={() => setEdit(u)}>Edit</button>{" "}
                      <button className="btn btn-xs" onClick={() => toggle(u)}>{u.is_active ? "Deactivate" : "Activate"}</button>{" "}
                      <button className="btn btn-xs btn-danger" onClick={() => remove(u)}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </Card>
      )}
      {edit && (
        <Modal title={edit.id ? `Edit ${edit.full_name}` : "Add interviewer"} onClose={() => setEdit(null)}>
          <InterviewerForm u={edit} onSaved={() => { setEdit(null); reload(true); }} />
        </Modal>
      )}
    </>
  );
}

function InterviewerForm({ u, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ full_name: u.full_name || "", email: u.email || "", mobile: u.mobile || "", designation: u.designation || "", password: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      if (u.id) {
        const body = { full_name: f.full_name, mobile: f.mobile, designation: f.designation };
        if (f.password) body.password = f.password;
        await api.patch(`/admin/interviewers/${u.id}`, body);
        toast.success("Interviewer updated");
      } else {
        await api.post("/admin/interviewers", { ...f, mobile: f.mobile || null });
        toast.success(`Account created. Share the credentials with ${f.full_name}.`);
      }
      onSaved();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <form className="form" onSubmit={save}>
      <Field label="Full name"><input required value={f.full_name} onChange={set("full_name")} /></Field>
      <Field label="Email (login)"><input type="email" required disabled={!!u.id} value={f.email} onChange={set("email")} /></Field>
      <div className="grid-2">
        <Field label="Mobile"><input value={f.mobile} onChange={set("mobile")} /></Field>
        <Field label="Designation"><input value={f.designation} onChange={set("designation")} /></Field>
      </div>
      <Field label={u.id ? "New password (leave blank to keep)" : "Password"}>
        <PasswordInput required={!u.id} minLength={6} value={f.password} onChange={set("password")} />
      </Field>
      <button className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
    </form>
  );
}

/* ------------------------------------------------------------------ registered candidates (read-only) */
export function Candidates() {
  const { data, loading, error } = useFetch(() => api.get("/admin/candidates"));
  const [view, setView] = useState(null);
  const [q, setQ] = useState("");
  const rows = (data || []).filter((c) => !q || `${c.full_name} ${c.email} ${c.mobile}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageHead title="Registered Candidates" sub="Candidates self-register. Admins can view them but not edit their accounts.">
        <input className="search" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
      </PageHead>
      <ErrorBox error={error} />
      {loading ? <Spinner /> : (
        <Card>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Name</th><th>Email</th><th>Mobile</th><th>Registered</th><th>Resume</th><th>Applications</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => setView(c.id)}>
                  <td><b>{c.full_name}</b></td><td>{c.email}</td><td>{c.mobile || "—"}</td><td>{fmtDate(c.created_at)}</td>
                  <td>{c.has_resume ? <Badge tone="green">Uploaded</Badge> : <Badge>None</Badge>}</td>
                  <td>{c.applications.length ? c.applications.map((a) => <div key={a.id} className="small">{a.jd_title} · <StatusBadge status={a.status} /></div>) : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}
      {view && <CandidateModal id={view} onClose={() => setView(null)} />}
    </>
  );
}

function CandidateModal({ id, onClose }) {
  const { data } = useFetch(() => api.get(`/admin/candidates/${id}`), [id]);
  return (
    <Modal title={data?.full_name || "Candidate"} wide onClose={onClose}>
      {!data ? <Spinner /> : (
        <>
          <p className="muted">{data.email} · {data.mobile} · registered {fmtDateTime(data.created_at)}</p>
          <h4>Applications</h4>
          {data.applications.length === 0 ? <p className="muted">No applications yet.</p> : (
            <ul className="plain-list">{data.applications.map((a) => (
              <li key={a.id}><Link to={`/admin/applications/${a.id}`} onClick={onClose}>{a.jd_title}</Link> — <StatusBadge status={a.status} /></li>
            ))}</ul>
          )}
          <h4>Resume {data.resume_filename && <span className="muted small">({data.resume_filename})</span>}</h4>
          {data.resume_text ? <pre className="resume-pre">{data.resume_text}</pre> : <p className="muted">No resume uploaded.</p>}
        </>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------------ audit logs */
export function AuditLogs() {
  const [action, setAction] = useState("");
  const { data, loading, error } = useFetch(() => api.get(`/admin/audit-logs?limit=500${action ? `&action=${action}` : ""}`), [action]);
  return (
    <>
      <PageHead title="Audit Logs" sub="Every status change, score and decision is recorded.">
        <input className="search" placeholder="Filter action (e.g. OFFER)" value={action} onChange={(e) => setAction(e.target.value)} />
      </PageHead>
      <ErrorBox error={error} />
      {loading ? <Spinner /> : (
        <Card>
          <div className="table-wrap"><table className="table compact">
            <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
            <tbody>
              {data.map((l) => (
                <tr key={l.id}>
                  <td className="nowrap small">{fmtDateTime(l.created_at)}</td>
                  <td>{l.actor} <span className="muted small">({l.role})</span></td>
                  <td><Badge tone="blue">{l.action}</Badge></td>
                  <td className="small">{l.entity}{l.entity_id ? ` #${l.entity_id}` : ""}</td>
                  <td className="small">{l.entity === "application" && l.entity_id ? <Link to={`/admin/applications/${l.entity_id}`}>{l.details}</Link> : l.details}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}
    </>
  );
}
