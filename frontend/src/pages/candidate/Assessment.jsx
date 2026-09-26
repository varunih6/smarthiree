/**
 * Proctored online assessment.
 *  - full screen required (exits are recorded and block the test until re-entered)
 *  - tab / window switches recorded
 *  - copy, paste, cut and right-click blocked + recorded
 *  - one question at a time, per-question timer, auto-submit on timeout
 *  - timer is server-side: refreshing the page does not reset it
 * All telemetry goes to the backend and is visible only to the Admin.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { Logo } from "../../components/Layout";
import { Spinner } from "../../components/ui";

const isFull = () => !!(document.fullscreenElement || document.webkitFullscreenElement);
const enterFull = async () => {
  const el = document.documentElement;
  try { await (el.requestFullscreen?.() || el.webkitRequestFullscreen?.()); } catch { /* browser may refuse */ }
};
const exitFull = () => { if (isFull()) (document.exitFullscreen?.() || document.webkitExitFullscreen?.())?.catch?.(() => {}); };

export default function Assessment() {
  const { appId } = useParams();
  const nav = useNavigate();
  const [info, setInfo] = useState(null);
  const [stage, setStage] = useState("rules"); // rules | running | done
  const [q, setQ] = useState(null);
  const [answer, setAnswer] = useState("");
  const [remaining, setRemaining] = useState(0);
  const [agree, setAgree] = useState(false);
  const [warning, setWarning] = useState("");
  const [fullscreenLost, setFullscreenLost] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const answerRef = useRef("");
  const qRef = useRef(null);
  const submittingRef = useRef(false);

  answerRef.current = answer;
  qRef.current = q;

  useEffect(() => {
    api.get(`/candidate/applications/${appId}/assessment`).then(setInfo).catch((e) => setError(e.message));
  }, [appId]);

  const send = useCallback((event, detail) => {
    api.post(`/candidate/applications/${appId}/assessment/telemetry`, { event, detail }).catch(() => {});
  }, [appId]);

  const showQuestion = (res) => {
    if (res.done) { setStage("done"); exitFull(); return; }
    setQ(res.question);
    setAnswer("");
    setRemaining(res.question.remaining_sec);
  };

  const start = async () => {
    setError("");
    await enterFull();
    try {
      const res = await api.post(`/candidate/applications/${appId}/assessment/start`);
      setStage("running");
      showQuestion(res);
    } catch (e) { setError(e.message); exitFull(); }
  };

  const submit = useCallback(async (timedOut = false) => {
    if (submittingRef.current || !qRef.current) return;
    submittingRef.current = true; setSubmitting(true);
    try {
      const res = await api.post(`/candidate/applications/${appId}/assessment/answer`, {
        answer_id: qRef.current.answer_id, answer: answerRef.current, timed_out: timedOut,
      });
      if (timedOut) setWarning("Time's up — your answer was submitted automatically.");
      showQuestion(res);
    } catch (e) {
      // question expired server-side / already answered -> fetch the current one
      try { showQuestion(await api.get(`/candidate/applications/${appId}/assessment/next`)); } catch { setError(e.message); }
    } finally { submittingRef.current = false; setSubmitting(false); }
  }, [appId]);

  // countdown per question
  useEffect(() => {
    if (stage !== "running" || !q) return;
    if (remaining <= 0) { submit(true); return; }
    const t = setTimeout(() => setRemaining((r) => r - 1), 1000);
    return () => clearTimeout(t);
  }, [remaining, stage, q, submit]);

  // anti-cheat listeners
  useEffect(() => {
    if (stage !== "running") return;
    let lastSwitch = 0;
    const recordSwitch = (kind) => {
      const now = Date.now();
      if (now - lastSwitch < 1500) return; // blur + visibilitychange fire together
      lastSwitch = now;
      send("tab_switch", kind);
      setWarning("⚠ Switching tabs/windows is not allowed. This has been recorded.");
    };
    const onVis = () => { if (document.hidden) recordSwitch("tab hidden"); };
    const onBlur = () => recordSwitch("window blur");
    const onFs = () => { if (!isFull()) { send("fullscreen_exit"); setFullscreenLost(true); } else setFullscreenLost(false); };
    const block = (type) => (e) => { e.preventDefault(); send(type); setWarning(`⚠ ${type === "paste" ? "Pasting" : "Copying"} is disabled during the assessment. This has been recorded.`); };
    const onCopy = block("copy"), onCut = block("copy"), onPaste = block("paste");
    const onCtx = (e) => { e.preventDefault(); send("context_menu"); };
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && ["c", "v", "x", "a"].includes(e.key.toLowerCase())) {
        e.preventDefault();
        if (e.key.toLowerCase() === "v") { send("paste", "shortcut"); setWarning("⚠ Pasting is disabled. This has been recorded."); }
        if (["c", "x"].includes(e.key.toLowerCase())) send("copy", "shortcut");
      }
      if (e.key === "F12" || e.key === "PrintScreen") e.preventDefault();
    };
    const beforeUnload = (e) => { e.preventDefault(); e.returnValue = ""; };

    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("webkitfullscreenchange", onFs);
    document.addEventListener("copy", onCopy);
    document.addEventListener("cut", onCut);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onCtx);
    document.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", beforeUnload);
    if (!isFull()) setFullscreenLost(true);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFs);
      document.removeEventListener("webkitfullscreenchange", onFs);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("cut", onCut);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onCtx);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [stage, send]);

  useEffect(() => { if (!warning) return; const t = setTimeout(() => setWarning(""), 4000); return () => clearTimeout(t); }, [warning]);

  /* ---------------------------------------------------------------- render */
  if (error && !info) return <div className="center-page"><div className="card"><p className="alert alert-error">{error}</p><Link to="/candidate" className="btn">Back to dashboard</Link></div></div>;
  if (!info) return <div className="center-page"><Spinner /></div>;

  if (stage === "done") {
    return (
      <div className="exam-shell center-page">
        <div className="card exam-done">
          <div className="success-icon">✓</div>
          <h1>Assessment submitted</h1>
          <p>Thank you! Your responses have been recorded. The hiring team will review them and you'll see the update on your dashboard.</p>
          <button className="btn btn-primary" onClick={() => nav("/candidate")}>Back to dashboard</button>
        </div>
      </div>
    );
  }

  if (stage === "rules") {
    const canStart = info.can_start;
    return (
      <div className="exam-shell center-page">
        <div className="card exam-rules">
          <Logo small />
          <h1>{info.jd_title} — Online Assessment</h1>
          <p className="muted">{info.num_questions} questions · about {Math.round(info.total_time_sec / 60)} minutes in total</p>
          {!canStart && <div className="alert alert-info">This assessment is not available (status: {info.status}).</div>}
          <h3>Rules</h3>
          <ul className="rules">{info.rules.map((r) => <li key={r}>{r}</li>)}</ul>
          {error && <div className="alert alert-error">{error}</div>}
          <label className="check"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> I understand the rules. Violations are recorded and shared with the hiring team.</label>
          <div className="btn-row">
            <Link to="/candidate" className="btn">Cancel</Link>
            <button className="btn btn-primary" disabled={!agree || !canStart} onClick={start}>{info.started ? "Resume in full screen" : "Start in full screen"}</button>
          </div>
        </div>
      </div>
    );
  }

  const pct = q ? ((q.index - 1) / q.total) * 100 : 0;
  const low = remaining <= 15;
  return (
    <div className="exam-shell noselect">
      <header className="exam-top">
        <Logo small />
        <div className="exam-progress">
          <div className="muted small">Question {q?.index} of {q?.total}</div>
          <div className="progress"><div style={{ width: `${pct}%` }} /></div>
        </div>
        <div className={`timer ${low ? "low" : ""}`}>⏱ {Math.floor(remaining / 60)}:{String(Math.max(0, remaining) % 60).padStart(2, "0")}</div>
      </header>
      {warning && <div className="exam-warning">{warning}</div>}
      {q && (
        <main className="exam-body">
          <div className="q-card">
            <div className="q-num">Q{q.index} <span className="badge badge-gray">{q.difficulty}</span></div>
            <h2 className="q-text">{q.text}</h2>
            <textarea className="answer" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Type your answer here…"
              autoFocus spellCheck={false} onPaste={(e) => e.preventDefault()} onDrop={(e) => e.preventDefault()} />
            <div className="row-between">
              <span className="muted small">{answer.trim().split(/\s+/).filter(Boolean).length} words · you cannot return to this question</span>
              <button className="btn btn-primary" disabled={submitting} onClick={() => submit(false)}>
                {q.index === q.total ? "Submit assessment" : "Save & next →"}
              </button>
            </div>
          </div>
        </main>
      )}
      {fullscreenLost && (
        <div className="fs-overlay">
          <div className="card center">
            <h2>Full screen required</h2>
            <p>You left full-screen mode. This has been recorded. Your timer is still running.</p>
            <button className="btn btn-primary" onClick={async () => { await enterFull(); if (isFull()) setFullscreenLost(false); }}>Return to full screen</button>
          </div>
        </div>
      )}
    </div>
  );
}
