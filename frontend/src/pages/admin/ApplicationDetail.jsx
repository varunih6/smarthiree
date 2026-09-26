import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { Badge, BandBadge, Card, ErrorBox, Flags, ScoreBar, Spinner, Stars, StatusBadge, fmtDateTime, fmtNum, useFetch } from "../../components/ui";
import { useToast } from "../../context";

const REC = {
  ADVANCE: ["green", "System recommends: advance to interview"],
  REVIEW: ["amber", "System recommends: manual review"],
  REJECT: ["red", "System recommends: reject"],
};

export default function ApplicationDetail() {
  const { id } = useParams();
  const toast = useToast();
  const { data: a, loading, error, reload, setData } = useFetch(() => api.get(`/admin/applications/${id}`), [id]);
  const [busy, setBusy] = useState(false);

  // poll while assessment answers are being scored
  useEffect(() => {
    if (a?.assessment_scoring !== "pending") return;
    const t = setInterval(() => reload(true), 1500);
    return () => clearInterval(t);
  }, [a?.assessment_scoring, reload]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const act = async (fn, msg) => {
    setBusy(true);
    try { const d = await fn(); if (d?.id) setData(d); else reload(true); toast.success(msg); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  const jd = a.jd;
  const hadInterview = a.evaluations.length > 0 || a.status === "INTERVIEW_COMPLETED";

  return (
    <>
      <Link to={`/admin/pipeline?jd=${a.jd_id}`} className="back-link">← Back to pipeline</Link>
      <PageHead title={a.candidate_name} sub={`${a.jd_title} · ${a.candidate_email} · ${a.candidate.mobile || ""} · Applied ${fmtDateTime(a.created_at)}`}>
        <StatusBadge status={a.status} /> <BandBadge band={a.band} />
      </PageHead>

      {/* ---------------- scores */}
      <div className="score-grid">
        <ScoreTile label="Resume (ATS)" value={a.resume_score} w={jd.weight_resume} sub={`threshold ${jd.ats_threshold}`} />
        <ScoreTile label="Assessment" value={a.assessment_pct} w={jd.weight_assessment}
          sub={a.assessment_scoring === "pending" ? "AI scoring…" : a.assessment_score != null ? `${a.assessment_score}/5 avg` : "not taken"} />
        <ScoreTile label="Interview" value={a.interview_score} w={jd.weight_interview} sub={a.interviewer_decision || "—"} />
        <div className="score-tile combined">
          <div className="st-label">Combined score</div>
          <div className="st-value">{fmtNum(a.combined_score, 1)}</div>
          <div className="st-sub">PASS ≥ {jd.pass_threshold} · HOLD ≥ {jd.hold_threshold}</div>
          <BandBadge band={a.band} />
        </div>
      </div>

      {a.flags.length > 0 && (
        <div className="alert alert-warn"><b>Auto-flags:</b> {a.flags.map((f) => f.label).join(" · ")}</div>
      )}

      <div className="detail-grid">
        <div className="detail-main">
          {/* ---------------- resume evidence */}
          <Card title="Resume evidence (AI)" actions={a.resume_source && <Badge tone={a.resume_source === "llm" ? "blue" : "gray"}>{a.resume_source}</Badge>}>
            {a.resume_score == null ? <p className="muted">Not scored yet.</p> : (
              <>
                <p>{a.resume_summary}</p>
                <div className="kv"><span>Matched skills</span><div className="chips">{a.matched_skills.map((s) => <Badge key={s} tone="green">{s}</Badge>)}</div></div>
                <div className="kv"><span>Gaps</span><div className="chips">{a.gaps.length ? a.gaps.map((s) => <Badge key={s} tone="red">{s}</Badge>) : <span className="muted">None</span>}</div></div>
                {a.archive_reason && <div className="alert alert-error small">Archived: {a.archive_reason}</div>}
              </>
            )}
            <details className="resume-text"><summary>View full resume text</summary><pre>{a.resume_text}</pre></details>
          </Card>

          {/* ---------------- assessment */}
          <Card title="Online assessment" actions={a.assessment_submitted_at && <span className="muted small">Submitted {fmtDateTime(a.assessment_submitted_at)}</span>}>
            {a.answers.length === 0 ? <p className="muted">Assessment not started.</p> : (
              <div className="qa-list">
                {a.answers.map((q) => (
                  <div key={q.order} className="qa">
                    <div className="qa-head">
                      <b>Q{q.order}. {q.question}</b>
                      <span className="qa-meta">
                        ⏱ {q.time_taken_sec ?? "—"}s / {q.time_limit_sec}s {q.timed_out && <Badge tone="amber">timed out</Badge>}
                      </span>
                    </div>
                    <div className="qa-answer">{q.answer || <i className="muted">No answer</i>}</div>
                    {q.score != null && (
                      <div className="qa-score">
                        <ScoreBar value={q.score} max={5} />
                        <span>confidence <b>{fmtNum(q.confidence, 2)}</b></span>
                        <Badge tone={q.source === "llm" ? "blue" : "gray"}>{q.source}</Badge>
                        <div className="muted small">{q.justification}</div>
                        <div className="chips">{q.rubric.map((r) => (
                          <Badge key={r} tone={q.rubric_hits.includes(r) ? "green" : "gray"}>{q.rubric_hits.includes(r) ? "✓" : "✗"} {r}</Badge>
                        ))}</div>
                      </div>
                    )}
                  </div>
                ))}
                <div className="muted small">Avg AI confidence: <b>{fmtNum(a.avg_confidence, 2)}</b> (cutoff {jd.confidence_cutoff})</div>
              </div>
            )}
          </Card>

          {/* ---------------- interviewer feedback */}
          <Card title="Interviewer feedback">
            {a.evaluations.length === 0 ? <p className="muted">No evaluation submitted yet.</p> : a.evaluations.map((e) => (
              <div key={e.id} className="eval">
                <div className="eval-head"><b>{e.interviewer}</b> <Badge tone={e.decision === "Accepted" ? "green" : e.decision === "Rejected" ? "red" : "amber"}>{e.decision}</Badge> <span className="muted small">{fmtDateTime(e.created_at)}</span></div>
                <div className="eval-grid">
                  {[["Technical skills", e.technical], ["Problem solving", e.problem_solving], ["Projects / experience", e.projects], ["Communication", e.communication], ["Overall", e.overall]].map(([l, v]) => (
                    <div key={l} className="eval-row"><span>{l}</span><Stars value={v} size={16} /></div>
                  ))}
                </div>
                <div className="muted">Average {e.average}/5</div>
                {e.comments && <p className="quote">“{e.comments}”</p>}
              </div>
            ))}
          </Card>
        </div>

        <div className="detail-side">
          <ActionPanel a={a} busy={busy} act={act} hadInterview={hadInterview} />

          {a.telemetry && (
            <Card title="Anti-cheat telemetry">
              <div className="telemetry">
                <div><b>{a.telemetry.tab_switches}</b><span>tab switches</span></div>
                <div><b>{a.telemetry.paste_events}</b><span>paste attempts</span></div>
                <div><b>{a.telemetry.copy_events}</b><span>copy attempts</span></div>
                <div><b>{a.telemetry.fullscreen_exits}</b><span>full-screen exits</span></div>
              </div>
              {a.telemetry.log.length > 0 && (
                <details><summary>Event log ({a.telemetry.log.length})</summary>
                  <ul className="plain-list small">{a.telemetry.log.map((l, i) => <li key={i}>{fmtDateTime(l.at)} — {l.event}{l.question ? ` (Q${l.question})` : ""}</li>)}</ul>
                </details>
              )}
            </Card>
          )}

          <NextSteps a={a} act={act} />
          <Notes a={a} act={act} />
        </div>
      </div>
    </>
  );
}

function ScoreTile({ label, value, w, sub }) {
  return (
    <div className="score-tile">
      <div className="st-label">{label} <span className="muted">· w {w}</span></div>
      <div className="st-value">{value == null ? "—" : fmtNum(value)}</div>
      <ScoreBar value={value} />
      <div className="st-sub">{sub}</div>
    </div>
  );
}

function ActionPanel({ a, busy, act, hadInterview }) {
  const post = (path, body, msg) => act(() => api.post(`/admin/applications/${a.id}/${path}`, body), msg);
  const s = a.status;

  if (["APPLIED", "FILTERED"].includes(s)) {
    return (
      <Card title="Actions">
        <p className="muted small">Candidate is below the ATS threshold or not scored. You can re-run scoring or manually override.</p>
        <button className="btn btn-block" disabled={busy} onClick={() => post("rescore", {}, "Resume re-scored")}>↻ Re-score resume</button>
        <button className="btn btn-primary btn-block" disabled={busy} onClick={() => post("review", { action: "PROMOTE" }, "Promoted to assessment")}>Promote to assessment (override)</button>
      </Card>
    );
  }
  if (["SCREENING", "ASSESSMENT_IN_PROGRESS"].includes(s)) {
    return <Card title="Actions"><p className="muted">Waiting for the candidate to complete the online assessment.</p>
      <button className="btn btn-danger btn-block" disabled={busy} onClick={() => post("review", { action: "REJECT" }, "Candidate rejected")}>Reject</button></Card>;
  }
  if (s === "ASSESSMENT_SUBMITTED" || (s === "ON_HOLD" && !hadInterview && !a.interview_at)) {
    const [tone, text] = REC[a.recommendation] || ["gray", a.assessment_scoring === "pending" ? "AI is scoring the answers…" : "No recommendation"];
    return (
      <Card title="Assessment review">
        <div className={`rec rec-${tone}`}>{text}</div>
        <button className="btn btn-primary btn-block" disabled={busy} onClick={() => post("review", { action: "APPROVE" }, "Approved for interview")}>✓ Approve for interview</button>
        <div className="btn-row">
          <button className="btn btn-block" disabled={busy || s === "ON_HOLD"} onClick={() => post("review", { action: "HOLD" }, "Put on hold")}>Hold</button>
          <button className="btn btn-danger btn-block" disabled={busy} onClick={() => post("review", { action: "REJECT" }, "Candidate rejected")}>Reject</button>
        </div>
      </Card>
    );
  }
  if (["INTERVIEW_PENDING", "INTERVIEW_SCHEDULED"].includes(s)) {
    return <SchedulePanel a={a} busy={busy} act={act} />;
  }
  if (s === "INTERVIEW_COMPLETED" || s === "ON_HOLD") {
    return (
      <Card title="Final decision">
        <p className="small">Combined score <b>{fmtNum(a.combined_score, 1)}</b> → <BandBadge band={a.band} /> · Interviewer says <b>{a.interviewer_decision || "—"}</b></p>
        <button className="btn btn-primary btn-block" disabled={busy} onClick={() => post("decision", { decision: "OFFER" }, "Offer released")}>🎉 Release offer</button>
        <div className="btn-row">
          <button className="btn btn-block" disabled={busy || s === "ON_HOLD"} onClick={() => post("decision", { decision: "HOLD" }, "On hold")}>Hold</button>
          <button className="btn btn-danger btn-block" disabled={busy} onClick={() => post("decision", { decision: "REJECT" }, "Candidate rejected")}>Reject</button>
        </div>
      </Card>
    );
  }
  return (
    <Card title="Outcome">
      <p><StatusBadge status={s} /></p>
      {a.decided_at && <p className="muted small">Decided {fmtDateTime(a.decided_at)}</p>}
      {a.candidate_response && <p>Candidate response: <b>{a.candidate_response}</b> ({fmtDateTime(a.responded_at)})</p>}
      {a.interview_at && <p className="muted small">Interviewed by {a.interviewer_name} on {fmtDateTime(a.interview_at)}</p>}
    </Card>
  );
}

function SchedulePanel({ a, busy, act }) {
  const { data } = useFetch(async () => {
    const [ivs, sched] = await Promise.all([api.get("/admin/interviewers"), api.get("/admin/schedule")]);
    return { ivs: ivs.filter((i) => i.is_active), slots: sched.slots };
  }, [a.id]);
  const [ivId, setIvId] = useState(a.interviewer_id || "");
  const [slotId, setSlotId] = useState("");
  const [custom, setCustom] = useState("");
  const free = (data?.slots || []).filter((s) => s.interviewer_id === Number(ivId) && !s.is_booked && new Date(s.start) > new Date());

  const submit = () => act(() => api.post(`/admin/applications/${a.id}/schedule`, {
    interviewer_id: Number(ivId), slot_id: slotId ? Number(slotId) : null, start: !slotId && custom ? custom : null,
  }), "Interview scheduled");

  return (
    <Card title={a.status === "INTERVIEW_SCHEDULED" ? "Interview scheduled" : "Assign interviewer & schedule"}>
      {a.interview_at && (
        <div className="rec rec-violet">📅 {fmtDateTime(a.interview_at)} with <b>{a.interviewer_name}</b> ({a.scheduled_by})</div>
      )}
      <p className="muted small">{a.status === "INTERVIEW_PENDING" ? "Pick a slot, or use Auto-schedule on the Scheduling page." : "Re-schedule if needed:"}</p>
      <label className="field"><span className="field-label">Interviewer</span>
        <select value={ivId} onChange={(e) => { setIvId(e.target.value); setSlotId(""); }}>
          <option value="">Select interviewer…</option>
          {data?.ivs.map((i) => <option key={i.id} value={i.id}>{i.full_name} ({i.free_slots} free)</option>)}
        </select>
      </label>
      {ivId && (
        <label className="field"><span className="field-label">Available slot</span>
          <select value={slotId} onChange={(e) => setSlotId(e.target.value)}>
            <option value="">{free.length ? "Choose a slot…" : "No free slots — use custom time"}</option>
            {free.map((s) => <option key={s.id} value={s.id}>{fmtDateTime(s.start)}</option>)}
          </select>
        </label>
      )}
      {ivId && !slotId && (
        <label className="field"><span className="field-label">…or custom date & time</span>
          <input type="datetime-local" value={custom} onChange={(e) => setCustom(e.target.value)} />
        </label>
      )}
      <button className="btn btn-primary btn-block" disabled={busy || !ivId || (!slotId && !custom)} onClick={submit}>
        {a.status === "INTERVIEW_SCHEDULED" ? "Re-schedule" : "Schedule interview"}
      </button>
    </Card>
  );
}

function NextSteps({ a, act }) {
  const [text, setText] = useState(a.next_steps || "");
  return (
    <Card title="Next steps">
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Schedule system-design round with Ananya" />
      <button className="btn btn-sm" disabled={!text.trim()} onClick={() => act(() => api.post(`/admin/applications/${a.id}/next-steps`, { text }), "Next steps saved")}>Save</button>
    </Card>
  );
}

function Notes({ a, act }) {
  const [text, setText] = useState("");
  return (
    <Card title={`Notes (${a.notes.length})`}>
      <ul className="notes">
        {a.notes.map((n) => <li key={n.id}><div className="note-meta"><b>{n.author}</b> · {n.role} · {fmtDateTime(n.created_at)}</div>{n.text}</li>)}
      </ul>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note…" />
      <button className="btn btn-sm" disabled={!text.trim()} onClick={() => { act(() => api.post(`/admin/applications/${a.id}/notes`, { text }), "Note added"); setText(""); }}>Add note</button>
    </Card>
  );
}
