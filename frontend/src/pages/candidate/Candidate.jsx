import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { Badge, Card, Empty, ErrorBox, Modal, Spinner, Timeline, fmtDate, fmtDateTime, useFetch } from "../../components/ui";
import { useAuth, useToast } from "../../context";

const LABEL_TONE = {
  "Not Shortlisted": "red", Rejected: "red", "Offer Released": "green", "Offer Accepted": "green",
  "Shortlisted for Assessment": "blue", "Shortlisted for Interview": "violet", "Interview Scheduled": "violet",
  "On Hold": "amber", "Assessment Completed": "amber", "Interview Completed": "amber",
};

/* ------------------------------------------------------------------ dashboard */
export function CandidateDashboard() {
  const { user } = useAuth();
  const toast = useToast();
  const profile = useFetch(() => api.get("/candidate/profile"));
  const apps = useFetch(() => api.get("/candidate/applications"));
  const [letter, setLetter] = useState(null);

  const respond = async (id, response) => {
    if (!window.confirm(`Are you sure you want to ${response === "ACCEPTED" ? "accept" : "decline"} this offer?`)) return;
    try {
      await api.post(`/candidate/applications/${id}/offer-response`, { response });
      toast.success(response === "ACCEPTED" ? "Offer accepted — welcome aboard! 🎉" : "Offer declined");
      apps.reload(true);
    } catch (e) { toast.error(e.message); }
  };
  const openLetter = async (id) => {
    try { setLetter(await api.get(`/candidate/applications/${id}/offer-letter`)); } catch (e) { toast.error(e.message); }
  };

  return (
    <>
      <PageHead title={`Hi, ${user.full_name.split(" ")[0]} 👋`} sub="Track your applications and keep your resume up to date.">
        <Link to="/candidate/jobs" className="btn btn-primary">Browse job openings</Link>
      </PageHead>
      <div className="grid-side">
        <div>
          <Card title="My applications">
            {apps.loading ? <Spinner /> : apps.error ? <ErrorBox error={apps.error} /> : apps.data.length === 0 ? (
              <Empty title="You haven't applied yet">Upload your resume and <Link to="/candidate/jobs">apply for a role</Link>.</Empty>
            ) : apps.data.map((a) => (
              <div key={a.id} className="app-card">
                <div className="row-between">
                  <div><h3>{a.jd_title}</h3><div className="muted small">{a.location} · Applied {fmtDate(a.applied_at)}</div></div>
                  <Badge tone={LABEL_TONE[a.status_label] || "gray"}>{a.status_label}</Badge>
                </div>
                <p className="status-msg">{a.status_message}</p>

                {a.can_take_assessment && (
                  <div className="cta-box">
                    <div><b>Online assessment unlocked</b><div className="muted small">Proctored · full screen · timed questions</div></div>
                    <Link to={`/candidate/assessment/${a.id}`} className="btn btn-primary">{a.status === "ASSESSMENT_IN_PROGRESS" ? "Resume assessment" : "Start assessment"}</Link>
                  </div>
                )}
                {a.interview && (
                  <div className="cta-box violet">
                    <div><b>📅 {fmtDateTime(a.interview.at)}</b><div className="muted small">Interviewer: {a.interview.interviewer} · {a.interview.mode}</div></div>
                  </div>
                )}
                {a.can_respond_offer && (
                  <div className="cta-box green">
                    <div><b>🎉 You have been selected!</b><div className="muted small">Please accept or decline your offer.</div></div>
                    <div className="btn-row">
                      <button className="btn" onClick={() => openLetter(a.id)}>View offer letter</button>
                      <button className="btn btn-danger" onClick={() => respond(a.id, "DECLINED")}>Decline</button>
                      <button className="btn btn-primary" onClick={() => respond(a.id, "ACCEPTED")}>Accept offer</button>
                    </div>
                  </div>
                )}
                {a.has_offer_letter && !a.can_respond_offer && (
                  <button className="btn btn-sm" onClick={() => openLetter(a.id)}>View / download offer letter</button>
                )}
                <details className="tl-details"><summary>Application timeline</summary><Timeline steps={a.timeline} /></details>
              </div>
            ))}
          </Card>
        </div>
        <div>
          <ResumeCard profile={profile} />
        </div>
      </div>
      {letter && <OfferLetter data={letter} onClose={() => setLetter(null)} />}
    </>
  );
}

function ResumeCard({ profile }) {
  const toast = useToast();
  const fileRef = useRef();
  const [paste, setPaste] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const p = profile.data;

  const upload = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setBusy(true);
    try { await api.upload("/candidate/resume", fd); toast.success("Resume uploaded"); profile.reload(true); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); fileRef.current.value = ""; }
  };
  const savePaste = async () => {
    setBusy(true);
    try { await api.post("/candidate/resume/text", { text }); toast.success("Resume saved"); setPaste(false); setText(""); profile.reload(true); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  return (
    <Card title="My resume">
      {profile.loading ? <Spinner /> : (
        <>
          {p?.resume_text ? (
            <div className="resume-box">
              <div className="resume-file">📄 {p.resume_filename}</div>
              <div className="muted small">Updated {fmtDateTime(p.resume_updated_at)}</div>
              <details><summary>Preview</summary><pre className="resume-pre">{p.resume_text}</pre></details>
            </div>
          ) : <div className="alert alert-info small">Upload your resume to see which roles match you best and to apply.</div>}
          <input ref={fileRef} type="file" accept=".txt,.md,text/plain" hidden onChange={(e) => upload(e.target.files[0])} />
          <div className="btn-row">
            <button className="btn btn-primary" disabled={busy} onClick={() => fileRef.current.click()}>{p?.resume_text ? "Replace" : "Upload"} (.txt)</button>
            <button className="btn" onClick={() => setPaste((x) => !x)}>Paste text</button>
          </div>
          {paste && (
            <div className="paste-box">
              <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste your full resume text here…" />
              <button className="btn btn-primary btn-sm" disabled={busy || text.trim().length < 30} onClick={savePaste}>Save resume</button>
            </div>
          )}
          <p className="muted small">Applications use the resume on file at the time you apply.</p>
        </>
      )}
    </Card>
  );
}

function OfferLetter({ data, onClose }) {
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Offer Letter - ${data.candidate}</title>
<style>body{font-family:Georgia,serif;max-width:720px;margin:40px auto;line-height:1.6;color:#222;padding:0 20px}h1{color:#00915a}.ref{color:#666}</style></head>
<body><h1>SmartHire — Offer of Employment</h1><p class="ref">Ref: ${data.reference} · Date: ${fmtDate(data.issued_on)}</p>
<p>Dear ${data.candidate},</p>
<p>We are delighted to offer you the position of <b>${data.role}</b> in our <b>${data.department}</b> team, based in <b>${data.location}</b>.</p>
<p>This offer follows your successful performance across our screening, online assessment and interview rounds. Details of compensation, joining date and onboarding will be shared by the HR team.</p>
<p>We look forward to welcoming you.</p><p>Warm regards,<br/>Hiring Team, SmartHire</p></body></html>`;
  const download = () => {
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const a = document.createElement("a"); a.href = url; a.download = `Offer_Letter_${data.reference}.html`; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Modal title="Offer letter" wide onClose={onClose}>
      <iframe title="offer" className="letter-frame" srcDoc={html} />
      <div className="btn-row"><button className="btn btn-primary" onClick={download}>Download</button></div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ jobs */
export function CandidateJobs() {
  const toast = useToast();
  const nav = useNavigate();
  const { data, loading, error, reload } = useFetch(() => api.get("/candidate/jobs"));
  const profile = useFetch(() => api.get("/candidate/profile"));
  const [view, setView] = useState(null);
  const [applying, setApplying] = useState(null);
  const [result, setResult] = useState(null);

  const apply = async (jd) => {
    setApplying(jd.id);
    try {
      const r = await api.post(`/candidate/jobs/${jd.id}/apply`);
      setResult({ ...r, title: jd.title }); setView(null); reload(true);
    } catch (e) { toast.error(e.message); } finally { setApplying(null); }
  };

  if (loading) return <Spinner />;
  const hasResume = !!profile.data?.resume_text;
  return (
    <>
      <PageHead title="Job Openings" sub={hasResume ? "Roles are ordered by how well they match your resume." : "Upload your resume on the dashboard to see match priority and apply."} />
      <ErrorBox error={error} />
      {!hasResume && !profile.loading && <div className="alert alert-info">You need a resume on file before applying. <Link to="/candidate">Upload it here</Link>.</div>}
      <div className="job-grid">
        {data.map((j) => (
          <div key={j.id} className="job-card">
            <div className="row-between"><h3>{j.title}</h3>
              {j.priority && <Badge tone={{ High: "green", Medium: "amber", Low: "gray" }[j.priority]}>{j.priority} match</Badge>}
            </div>
            <div className="muted small">{j.department} · {j.location} · {j.experience}</div>
            <p className="clamp">{j.description}</p>
            <div className="chips">{j.must_have_skills.map((s) => <Badge key={s} tone="blue">{s}</Badge>)}</div>
            <div className="row-between">
              <button className="btn btn-sm" onClick={() => setView(j)}>Details</button>
              {j.applied ? <button className="btn btn-sm" onClick={() => nav("/candidate")}>Applied ✓ — view status</button>
                : <button className="btn btn-sm btn-primary" disabled={!hasResume || applying === j.id} onClick={() => apply(j)}>{applying === j.id ? "Screening…" : "Apply"}</button>}
            </div>
          </div>
        ))}
      </div>
      {data.length === 0 && <Empty title="No open roles right now" />}

      {view && (
        <Modal title={view.title} onClose={() => setView(null)}>
          <p className="muted">{view.department} · {view.location} · {view.experience}</p>
          <p>{view.description}</p>
          <h4>Must-have skills</h4><div className="chips">{view.must_have_skills.map((s) => <Badge key={s} tone="blue">{s}</Badge>)}</div>
          {view.nice_to_have_skills.length > 0 && <><h4>Nice to have</h4><div className="chips">{view.nice_to_have_skills.map((s) => <Badge key={s}>{s}</Badge>)}</div></>}
          <div className="btn-row" style={{ marginTop: 16 }}>
            {!view.applied && <button className="btn btn-primary" disabled={!hasResume || applying} onClick={() => apply(view)}>{applying ? "Screening your resume…" : "Apply now"}</button>}
          </div>
        </Modal>
      )}
      {result && (
        <Modal title={result.title} onClose={() => setResult(null)}>
          <div className="center">
            <div className={`success-icon ${result.passed ? "" : "fail"}`}>{result.passed ? "✓" : "✕"}</div>
            <h3>{result.passed ? "Initial screening cleared!" : "Application not shortlisted"}</h3>
            <p>{result.message}</p>
            {result.passed
              ? <Link className="btn btn-primary" to={`/candidate/assessment/${result.application.id}`}>Go to online assessment</Link>
              : <button className="btn" onClick={() => setResult(null)}>Explore other roles</button>}
          </div>
        </Modal>
      )}
    </>
  );
}
