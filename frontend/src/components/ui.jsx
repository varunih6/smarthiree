import { useCallback, useEffect, useState } from "react";

/* ---------------------------------------------------------------- helpers */
export const fmtDate = (s) =>
  s ? new Date(s).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";
export const fmtDateTime = (s) =>
  s ? new Date(s).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
export const fmtNum = (n, d = 0) => (n === null || n === undefined ? "—" : Number(n).toFixed(d));

/** useFetch(fn, deps) -> {data, loading, error, reload, setData} */
export function useFetch(fn, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setState((s) => ({ ...s, loading: true }));
    try {
      const data = await fn();
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e.message }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load, setData: (d) => setState((s) => ({ ...s, data: d })) };
}

/* ---------------------------------------------------------------- atoms */
export const Spinner = ({ label = "Loading…" }) => (
  <div className="spinner-row"><span className="spinner" /> {label}</div>
);

export const Empty = ({ title = "Nothing here yet", children }) => (
  <div className="empty"><div className="empty-title">{title}</div>{children}</div>
);

export const ErrorBox = ({ error }) => error ? <div className="alert alert-error">{error}</div> : null;

export function Card({ title, actions, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          {title && <h3>{title}</h3>}
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export const Stat = ({ label, value, tone = "" }) => (
  <div className={`stat ${tone}`}><div className="stat-label">{label}</div><div className="stat-value">{value}</div></div>
);

const STATUS_TONE = {
  APPLIED: "gray", FILTERED: "red", SCREENING: "blue", ASSESSMENT_IN_PROGRESS: "blue",
  ASSESSMENT_SUBMITTED: "amber", INTERVIEW_PENDING: "violet", INTERVIEW_SCHEDULED: "violet",
  INTERVIEW_COMPLETED: "amber", ON_HOLD: "amber", OFFERED: "green", REJECTED: "red",
  OFFER_ACCEPTED: "green", OFFER_DECLINED: "gray",
};
export const STATUS_LABEL = {
  APPLIED: "Applied (unscored)", FILTERED: "Filtered", SCREENING: "Screening",
  ASSESSMENT_IN_PROGRESS: "Assessment running", ASSESSMENT_SUBMITTED: "Assessment done",
  INTERVIEW_PENDING: "Interview pending", INTERVIEW_SCHEDULED: "Interview scheduled",
  INTERVIEW_COMPLETED: "Interview done", ON_HOLD: "On hold", OFFERED: "Offered",
  REJECTED: "Rejected", OFFER_ACCEPTED: "Offer accepted", OFFER_DECLINED: "Offer declined",
};
export const Badge = ({ tone = "gray", children, title }) => <span className={`badge badge-${tone}`} title={title}>{children}</span>;
export const StatusBadge = ({ status }) => <Badge tone={STATUS_TONE[status] || "gray"}>{STATUS_LABEL[status] || status}</Badge>;
export const BandBadge = ({ band }) =>
  band ? <Badge tone={{ PASS: "green", HOLD: "amber", REJECT: "red" }[band]}>{band}</Badge> : <span className="muted">—</span>;

export function Flags({ flags }) {
  if (!flags?.length) return <span className="muted">—</span>;
  return (
    <span className="flags">
      {flags.map((f) => (
        <Badge key={f.code} tone={f.severity === "danger" ? "red" : f.severity === "warn" ? "amber" : "gray"} title={f.label}>
          ⚑ {f.code.replace("_", " ").toLowerCase()}
        </Badge>
      ))}
    </span>
  );
}

export function ScoreBar({ value, max = 100, label }) {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tone = pct >= 70 ? "green" : pct >= 50 ? "amber" : "red";
  return (
    <div className="scorebar" title={label}>
      <div className="scorebar-track"><div className={`scorebar-fill fill-${tone}`} style={{ width: `${pct}%` }} /></div>
      <span className="scorebar-num">{fmtNum(value, max <= 5 ? 1 : 0)}{max <= 5 ? "/5" : ""}</span>
    </div>
  );
}

export function Stars({ value, onChange, size = 22 }) {
  return (
    <span className="stars">
      {[1, 2, 3, 4, 5].map((n) => (
        <button type="button" key={n} className={`star ${n <= value ? "on" : ""}`} style={{ fontSize: size }}
          onClick={() => onChange && onChange(n)} disabled={!onChange} aria-label={`${n} star`}>★</button>
      ))}
    </span>
  );
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const h = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose}>✕</button></div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Timeline({ steps }) {
  return (
    <ol className="timeline">
      {steps.map((s, i) => (
        <li key={i} className={`tl-item ${s.done ? "done" : ""} ${s.bad ? "bad" : ""}`}>
          <span className="tl-dot" />
          <div><div className="tl-label">{s.label}</div>{s.date && <div className="tl-date">{fmtDateTime(s.date)}</div>}</div>
        </li>
      ))}
    </ol>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function PasswordInput(props) {
  const [show, setShow] = useState(false);
  return (
    <div className="pw-wrap">
      <input {...props} type={show ? "text" : "password"} />
      <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)} tabIndex={-1}>
        {show ? "Hide" : "Show"}
      </button>
    </div>
  );
}
