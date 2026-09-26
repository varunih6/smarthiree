import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { Badge, Card, Empty, ErrorBox, Field, Modal, Spinner, useFetch } from "../../components/ui";
import { useToast } from "../../context";

const BLANK = {
  title: "", department: "Engineering", location: "Bengaluru", experience: "0-2 years", description: "",
  must_have_skills: [], nice_to_have_skills: [], ats_threshold: 60, weight_resume: 0.4, weight_assessment: 0.3,
  weight_interview: 0.3, pass_threshold: 70, hold_threshold: 50, confidence_cutoff: 0.6, num_questions: 5, is_active: true,
};

export default function Jobs() {
  const { data, loading, error, reload } = useFetch(() => api.get("/admin/jobs"));
  const [creating, setCreating] = useState(false);
  const nav = useNavigate();
  if (loading) return <Spinner />;
  return (
    <>
      <PageHead title="Job Descriptions" sub="Create roles and configure screening weights, thresholds and the question bank.">
        <button className="btn btn-primary" onClick={() => setCreating(true)}>+ New job</button>
      </PageHead>
      <ErrorBox error={error} />
      <div className="job-grid">
        {data.map((j) => (
          <div key={j.id} className="job-card clickable" onClick={() => nav(`/admin/jobs/${j.id}`)}>
            <div className="row-between"><h3>{j.title}</h3>{j.is_active ? <Badge tone="green">Open</Badge> : <Badge>Closed</Badge>}</div>
            <div className="muted small">{j.department} · {j.location} · {j.experience}</div>
            <div className="chips">{j.must_have_skills.slice(0, 6).map((s) => <Badge key={s} tone="blue">{s}</Badge>)}</div>
            <div className="job-meta">
              <span><b>{j.applications}</b> applicants</span><span><b>{j.question_count}</b> questions</span>
              <span>ATS ≥ <b>{j.ats_threshold}</b></span>
            </div>
            <div className="row-between">
              <Link to={`/admin/pipeline?jd=${j.id}`} className="btn btn-sm" onClick={(e) => e.stopPropagation()}>View pipeline</Link>
              <span className="link small">Edit →</span>
            </div>
          </div>
        ))}
      </div>
      {creating && (
        <Modal title="New job description" wide onClose={() => setCreating(false)}>
          <JDForm initial={BLANK} onSaved={(jd) => { setCreating(false); reload(); nav(`/admin/jobs/${jd.id}`); }} />
        </Modal>
      )}
    </>
  );
}

function JDForm({ initial, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ ...initial, must: initial.must_have_skills.join(", "), nice: initial.nice_to_have_skills.join(", ") });
  const [busy, setBusy] = useState(false);
  const set = (k, num) => (e) => setF({ ...f, [k]: num ? Number(e.target.value) : e.target.value });
  const wsum = (f.weight_resume + f.weight_assessment + f.weight_interview).toFixed(2);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    const body = { ...f, must_have_skills: split(f.must), nice_to_have_skills: split(f.nice) };
    delete body.must; delete body.nice;
    try {
      const jd = initial.id ? await api.put(`/admin/jobs/${initial.id}`, body) : await api.post("/admin/jobs", body);
      toast.success("Job saved");
      onSaved(jd);
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={save} className="form">
      <div className="grid-2">
        <Field label="Title"><input required value={f.title} onChange={set("title")} /></Field>
        <Field label="Department"><input value={f.department} onChange={set("department")} /></Field>
        <Field label="Location"><input value={f.location} onChange={set("location")} /></Field>
        <Field label="Experience"><input value={f.experience} onChange={set("experience")} placeholder="2-4 years" /></Field>
      </div>
      <Field label="Description"><textarea rows={3} value={f.description} onChange={set("description")} /></Field>
      <Field label="Must-have skills" hint="comma separated"><input value={f.must} onChange={set("must")} placeholder="Java, Spring Boot, SQL" /></Field>
      <Field label="Nice-to-have skills" hint="comma separated"><input value={f.nice} onChange={set("nice")} /></Field>

      <h4 className="section-title">Screening configuration</h4>
      <div className="grid-3">
        <Slider label="ATS pass threshold (resume score)" value={f.ats_threshold} min={0} max={100} step={1} onChange={set("ats_threshold", true)} />
        <Slider label="PASS band ≥ (combined)" value={f.pass_threshold} min={0} max={100} step={1} onChange={set("pass_threshold", true)} />
        <Slider label="HOLD band ≥ (combined)" value={f.hold_threshold} min={0} max={100} step={1} onChange={set("hold_threshold", true)} />
        <Slider label="Resume weight" value={f.weight_resume} min={0} max={1} step={0.05} onChange={set("weight_resume", true)} />
        <Slider label="Assessment weight" value={f.weight_assessment} min={0} max={1} step={0.05} onChange={set("weight_assessment", true)} />
        <Slider label="Interview weight" value={f.weight_interview} min={0} max={1} step={0.05} onChange={set("weight_interview", true)} />
        <Slider label="AI confidence cutoff (flag below)" value={f.confidence_cutoff} min={0} max={1} step={0.05} onChange={set("confidence_cutoff", true)} />
        <Field label="Questions per assessment"><input type="number" min={1} max={20} value={f.num_questions} onChange={set("num_questions", true)} /></Field>
        <Field label="Status">
          <select value={f.is_active ? "1" : "0"} onChange={(e) => setF({ ...f, is_active: e.target.value === "1" })}>
            <option value="1">Open (visible to candidates)</option><option value="0">Closed</option>
          </select>
        </Field>
      </div>
      <p className="muted small">Weights are normalised over the stages completed so far (current sum {wsum}).</p>
      <button className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Save job"}</button>
    </form>
  );
}

const split = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

function Slider({ label, value, onChange, ...rest }) {
  return (
    <label className="field">
      <span className="field-label">{label}: <b>{value}</b></span>
      <input type="range" value={value} onChange={onChange} {...rest} />
    </label>
  );
}

/* ------------------------------------------------------------------ JD detail + question bank */
export function JobDetail() {
  const { id } = useParams();
  const toast = useToast();
  const nav = useNavigate();
  const { data, loading, error, reload } = useFetch(() => api.get(`/admin/jobs/${id}`), [id]);
  const [q, setQ] = useState(null);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const del = async () => {
    if (!window.confirm("Delete / close this job?")) return;
    try { const r = await api.del(`/admin/jobs/${id}`); toast.info(r.message); nav("/admin/jobs"); } catch (e) { toast.error(e.message); }
  };
  const delQ = async (qid) => {
    try { await api.del(`/admin/questions/${qid}`); toast.success("Question deleted"); reload(true); } catch (e) { toast.error(e.message); }
  };

  return (
    <>
      <Link to="/admin/jobs" className="back-link">← All jobs</Link>
      <PageHead title={data.title} sub={`${data.department} · ${data.location}`}>
        <Link to={`/admin/pipeline?jd=${id}`} className="btn">View pipeline</Link>
        <button className="btn btn-danger" onClick={del}>Delete</button>
      </PageHead>
      <div className="grid-2 align-start">
        <Card title="Job details & screening rules">
          <JDForm key={data.id + JSON.stringify(data).length} initial={data} onSaved={() => reload(true)} />
        </Card>
        <Card title={`Question bank (${data.questions.length})`} actions={<button className="btn btn-sm btn-primary" onClick={() => setQ({ text: "", rubric: [], difficulty: "medium", time_limit_sec: 120 })}>+ Add question</button>}>
          {data.questions.length === 0 ? <Empty title="No questions yet" /> : (
            <ol className="qbank">
              {data.questions.map((x) => (
                <li key={x.id}>
                  <div className="row-between"><b>{x.text}</b>
                    <span className="nowrap"><button className="btn btn-xs" onClick={() => setQ(x)}>Edit</button> <button className="btn btn-xs btn-danger" onClick={() => delQ(x.id)}>✕</button></span>
                  </div>
                  <div className="muted small">{x.difficulty} · {x.time_limit_sec}s</div>
                  <ul className="rubric">{x.rubric.map((r) => <li key={r}>{r}</li>)}</ul>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
      {q && <Modal title={q.id ? "Edit question" : "New question"} onClose={() => setQ(null)}>
        <QuestionForm jdId={id} q={q} onSaved={() => { setQ(null); reload(true); }} />
      </Modal>}
    </>
  );
}

function QuestionForm({ jdId, q, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ ...q, rubricText: (q.rubric || []).join("\n") });
  const save = async (e) => {
    e.preventDefault();
    const body = { text: f.text, difficulty: f.difficulty, time_limit_sec: Number(f.time_limit_sec), rubric: f.rubricText.split("\n").map((s) => s.trim()).filter(Boolean) };
    try {
      if (q.id) await api.put(`/admin/questions/${q.id}`, body); else await api.post(`/admin/jobs/${jdId}/questions`, body);
      toast.success("Question saved"); onSaved();
    } catch (err) { toast.error(err.message); }
  };
  return (
    <form onSubmit={save} className="form">
      <Field label="Question"><textarea required rows={3} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></Field>
      <Field label="Rubric points" hint="one per line — the AI grades against these"><textarea rows={5} value={f.rubricText} onChange={(e) => setF({ ...f, rubricText: e.target.value })} /></Field>
      <div className="grid-2">
        <Field label="Difficulty"><select value={f.difficulty} onChange={(e) => setF({ ...f, difficulty: e.target.value })}><option>easy</option><option>medium</option><option>hard</option></select></Field>
        <Field label="Time limit (seconds)"><input type="number" min={15} max={1800} value={f.time_limit_sec} onChange={(e) => setF({ ...f, time_limit_sec: e.target.value })} /></Field>
      </div>
      <button className="btn btn-primary">Save question</button>
    </form>
  );
}
