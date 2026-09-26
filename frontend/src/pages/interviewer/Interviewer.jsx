import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { Badge, Card, Empty, ErrorBox, ScoreBar, Spinner, Stars, StatusBadge, fmtDateTime, fmtNum, useFetch } from "../../components/ui";
import { useToast } from "../../context";

const HOURS = [9, 10, 11, 12, 13, 14, 15, 16, 17];
const pad = (n) => String(n).padStart(2, "0");
const localIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;

/* ------------------------------------------------------------------ availability grid */
export function Availability() {
  const toast = useToast();
  const { data, loading, error, reload } = useFetch(() => api.get("/interviewer/availability"));
  const [offset, setOffset] = useState(0);
  const [busyCell, setBusyCell] = useState(null);

  const days = useMemo(() => {
    const out = [];
    const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + offset * 7);
    for (let i = 0; i < 7; i++) { const x = new Date(d); x.setDate(d.getDate() + i); out.push(x); }
    return out;
  }, [offset]);

  const slotMap = useMemo(() => {
    const m = {};
    (data || []).forEach((s) => { m[s.start.slice(0, 16)] = s; });
    return m;
  }, [data]);

  const toggle = async (day, hour) => {
    const d = new Date(day); d.setHours(hour, 0, 0, 0);
    if (d < new Date()) return;
    const key = localIso(d).slice(0, 16);
    const existing = slotMap[key];
    if (existing?.is_booked) return toast.info("This slot already has an interview booked");
    setBusyCell(key);
    try {
      if (existing) await api.del(`/interviewer/availability/${existing.id}`);
      else await api.post("/interviewer/availability", { starts: [localIso(d)], duration_min: 60 });
      await reload(true);
    } catch (e) { toast.error(e.message); } finally { setBusyCell(null); }
  };

  const fillWeek = async () => {
    const starts = [];
    days.forEach((day) => {
      if ([0, 6].includes(day.getDay())) return;
      [10, 11, 14, 15, 16].forEach((h) => { const d = new Date(day); d.setHours(h, 0, 0, 0); if (d > new Date()) starts.push(localIso(d)); });
    });
    try { const r = await api.post("/interviewer/availability", { starts, duration_min: 60 }); toast.success(`${r.added} slot(s) added`); reload(true); }
    catch (e) { toast.error(e.message); }
  };

  if (loading) return <Spinner />;
  const free = (data || []).filter((s) => !s.is_booked).length;
  const booked = (data || []).filter((s) => s.is_booked).length;

  return (
    <>
      <PageHead title="My Availability" sub="Click cells to mark when you are free. The admin's scheduler books candidates only into these slots.">
        <button className="btn" onClick={fillWeek}>Quick-fill weekdays (10-12, 14-17)</button>
      </PageHead>
      <ErrorBox error={error} />
      <Card title={`${free} free · ${booked} booked`} actions={
        <div className="btn-row">
          <button className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(offset - 1)}>← Prev</button>
          <button className="btn btn-sm" onClick={() => setOffset(offset + 1)}>Next →</button>
        </div>}>
        <div className="table-wrap">
          <table className="avail-grid">
            <thead><tr><th />{days.map((d) => <th key={d.toISOString()}>{d.toLocaleDateString("en-IN", { weekday: "short" })}<div className="muted small">{d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</div></th>)}</tr></thead>
            <tbody>
              {HOURS.map((h) => (
                <tr key={h}>
                  <td className="hour">{h > 12 ? h - 12 : h}:00 {h >= 12 ? "PM" : "AM"}</td>
                  {days.map((day) => {
                    const d = new Date(day); d.setHours(h, 0, 0, 0);
                    const key = localIso(d).slice(0, 16);
                    const s = slotMap[key];
                    const past = d < new Date();
                    const cls = s?.is_booked ? "booked" : s ? "free" : past ? "past" : "";
                    return (
                      <td key={key}>
                        <button className={`cell ${cls} ${busyCell === key ? "busy" : ""}`} disabled={past} onClick={() => toggle(day, h)}
                          title={s?.is_booked ? "Interview booked" : s ? "Available — click to remove" : "Click to mark available"}>
                          {s?.is_booked ? "Booked" : s ? "✓" : ""}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="legend"><span className="cell free">✓</span> available <span className="cell booked">Booked</span> interview <span className="cell" /> not available</div>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ assigned interviews */
export function Interviews() {
  const nav = useNavigate();
  const { data, loading, error } = useFetch(() => api.get("/interviewer/interviews"));
  if (loading) return <Spinner />;
  const upcoming = (data || []).filter((a) => a.status === "INTERVIEW_SCHEDULED");
  const done = (data || []).filter((a) => a.status !== "INTERVIEW_SCHEDULED");
  const Row = ({ a }) => (
    <tr className="clickable" onClick={() => nav(`/interviewer/interviews/${a.id}`)}>
      <td className="nowrap"><b>{fmtDateTime(a.interview_at)}</b></td>
      <td><b>{a.candidate_name}</b><div className="muted small">{a.candidate_email}</div></td>
      <td>{a.jd_title}</td>
      <td><ScoreBar value={a.resume_score} /></td><td><ScoreBar value={a.assessment_pct} /></td>
      <td>{a.interviewer_decision ? <Badge tone={a.interviewer_decision === "Accepted" ? "green" : a.interviewer_decision === "Rejected" ? "red" : "amber"}>{a.interviewer_decision}</Badge> : <StatusBadge status={a.status} />}</td>
      <td><button className="btn btn-sm btn-primary">{a.evaluated ? "View" : "Start interview"}</button></td>
    </tr>
  );
  const head = <thead><tr><th>When</th><th>Candidate</th><th>Role</th><th>Resume</th><th>Assessment</th><th>Status</th><th /></tr></thead>;
  return (
    <>
      <PageHead title="Assigned Interviews" sub="Only candidates assigned to you are shown." />
      <ErrorBox error={error} />
      <div className="stats">
        <div className="stat violet"><div className="stat-label">Upcoming</div><div className="stat-value">{upcoming.length}</div></div>
        <div className="stat green"><div className="stat-label">Completed</div><div className="stat-value">{done.length}</div></div>
      </div>
      <Card title="Upcoming">
        {upcoming.length ? <div className="table-wrap"><table className="table">{head}<tbody>{upcoming.map((a) => <Row key={a.id} a={a} />)}</tbody></table></div>
          : <Empty title="No upcoming interviews">Make sure your <Link to="/interviewer/availability">availability</Link> is up to date.</Empty>}
      </Card>
      {done.length > 0 && <Card title="Completed"><div className="table-wrap"><table className="table">{head}<tbody>{done.map((a) => <Row key={a.id} a={a} />)}</tbody></table></div></Card>}
    </>
  );
}

/* ------------------------------------------------------------------ interview room */
const CRITERIA = [["technical", "Technical skills"], ["problem_solving", "Problem solving"], ["projects", "Projects / experience"], ["communication", "Communication (soft skills)"], ["overall", "Overall"]];

export function InterviewDetail() {
  const { id } = useParams();
  const toast = useToast();
  const { data: a, loading, error, reload } = useFetch(() => api.get(`/interviewer/interviews/${id}`), [id]);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const mine = a.evaluations[0];

  return (
    <>
      <Link to="/interviewer" className="back-link">← Assigned interviews</Link>
      <div className="page-head">
        <div><h1>{a.candidate_name}</h1><p className="muted">{a.jd_title} · {fmtDateTime(a.interview_at)}</p></div>
        <div className="page-actions"><StatusBadge status={a.status} /></div>
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          <Card title="AI evidence">
            <div className="score-grid mini">
              <div className="score-tile"><div className="st-label">Resume match</div><div className="st-value">{fmtNum(a.resume_score)}</div><ScoreBar value={a.resume_score} /></div>
              <div className="score-tile"><div className="st-label">Assessment</div><div className="st-value">{fmtNum(a.assessment_pct)}</div><ScoreBar value={a.assessment_pct} /></div>
              <div className="score-tile"><div className="st-label">AI confidence</div><div className="st-value">{fmtNum(a.avg_confidence, 2)}</div></div>
            </div>
            <p>{a.resume_summary}</p>
            <div className="kv"><span>Matched</span><div className="chips">{a.matched_skills.map((s) => <Badge key={s} tone="green">{s}</Badge>)}</div></div>
            <div className="kv"><span>Gaps</span><div className="chips">{a.gaps.length ? a.gaps.map((s) => <Badge key={s} tone="red">{s}</Badge>) : <span className="muted">None</span>}</div></div>
            <details className="resume-text"><summary>Resume</summary><pre>{a.resume_text}</pre></details>
          </Card>
          <Card title="Assessment answers">
            {a.answers.length === 0 ? <p className="muted">No assessment data.</p> : a.answers.map((q) => (
              <div key={q.order} className="qa">
                <div className="qa-head"><b>Q{q.order}. {q.question}</b><span className="qa-meta">{q.time_taken_sec ?? "—"}s</span></div>
                <div className="qa-answer">{q.answer || <i className="muted">No answer</i>}</div>
                {q.score != null && <div className="qa-score"><ScoreBar value={q.score} max={5} /><span>confidence <b>{fmtNum(q.confidence, 2)}</b></span><div className="muted small">{q.justification}</div></div>}
              </div>
            ))}
          </Card>
        </div>
        <div className="detail-side">
          <EvaluationForm a={a} existing={mine} onSaved={() => reload(true)} />
          <StatusToggles a={a} onSaved={() => reload(true)} />
          <InterviewerNotes a={a} onSaved={() => reload(true)} toast={toast} />
        </div>
      </div>
    </>
  );
}

function EvaluationForm({ a, existing, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState(existing ? { ...existing } : { technical: 0, problem_solving: 0, projects: 0, communication: 0, overall: 0, comments: "", decision: "Accepted" });
  const [busy, setBusy] = useState(false);
  const complete = CRITERIA.every(([k]) => f[k] > 0);
  const submit = async (e) => {
    e.preventDefault();
    if (!complete) return toast.error("Please rate every criterion");
    setBusy(true);
    try {
      await api.post(`/interviewer/interviews/${a.id}/evaluation`, {
        technical: f.technical, problem_solving: f.problem_solving, projects: f.projects,
        communication: f.communication, overall: f.overall, comments: f.comments, decision: f.decision,
      });
      toast.success("Evaluation submitted to the hiring manager"); onSaved();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <Card title={existing ? "Your evaluation (editable)" : "Evaluation form"}>
      <form onSubmit={submit} className="form">
        {CRITERIA.map(([k, l]) => (
          <div key={k} className="eval-row"><span>{l}</span><Stars value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} /></div>
        ))}
        <label className="field"><span className="field-label">Decision</span>
          <select value={f.decision} onChange={(e) => setF({ ...f, decision: e.target.value })}>
            <option>Accepted</option><option>Rejected</option><option>On-Hold</option><option>No-Show</option>
          </select>
        </label>
        <label className="field"><span className="field-label">Comments</span>
          <textarea rows={3} value={f.comments} onChange={(e) => setF({ ...f, comments: e.target.value })} placeholder="Strengths, concerns, recommendation…" />
        </label>
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Submitting…" : existing ? "Update evaluation" : "Submit evaluation"}</button>
      </form>
    </Card>
  );
}

function StatusToggles({ a, onSaved }) {
  const toast = useToast();
  const set = async (decision) => {
    try { await api.post(`/interviewer/interviews/${a.id}/status`, { decision }); toast.success(`Marked ${decision}`); onSaved(); }
    catch (e) { toast.error(e.message); }
  };
  return (
    <Card title="Candidate status">
      <div className="toggle-group">
        {["Accepted", "Rejected", "On-Hold", "No-Show"].map((d) => (
          <button key={d} className={`toggle ${a.interviewer_decision === d ? "on" : ""}`} onClick={() => set(d)}>{d}</button>
        ))}
      </div>
    </Card>
  );
}

function InterviewerNotes({ a, onSaved, toast }) {
  const [text, setText] = useState("");
  const add = async () => {
    try { await api.post(`/interviewer/interviews/${a.id}/notes`, { text }); setText(""); toast.success("Note saved"); onSaved(); }
    catch (e) { toast.error(e.message); }
  };
  return (
    <Card title="Timestamped notes">
      <ul className="notes">{a.notes.map((n) => <li key={n.id}><div className="note-meta"><b>{n.author}</b> · {fmtDateTime(n.created_at)}</div>{n.text}</li>)}</ul>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note…" />
      <button className="btn btn-sm" disabled={!text.trim()} onClick={add}>Add note</button>
    </Card>
  );
}
