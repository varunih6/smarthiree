import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { Badge, Card, Empty, ErrorBox, Spinner, StatusBadge, fmtDateTime, fmtNum, useFetch } from "../../components/ui";
import { useToast } from "../../context";

export default function Schedule() {
  const toast = useToast();
  const { data, loading, error, reload } = useFetch(() => api.get("/admin/schedule"));
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const auto = async () => {
    setBusy(true);
    try {
      const r = await api.post("/admin/schedule/auto");
      setResult(r);
      toast.success(`${r.scheduled.length} interview(s) scheduled automatically`);
      reload(true);
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  // availability grid: interviewer -> day -> slots
  const grid = useMemo(() => {
    if (!data) return [];
    const by = {};
    data.slots.forEach((s) => {
      const day = s.start.slice(0, 10);
      by[s.interviewer] ??= {};
      (by[s.interviewer][day] ??= []).push(s);
    });
    return Object.entries(by);
  }, [data]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  return (
    <>
      <PageHead title="Interview Scheduling" sub="Interviewers publish their free slots; the smart scheduler matches waiting candidates to the earliest free slot, balancing interviewer load.">
        <button className="btn btn-primary" disabled={busy || data.pending.length === 0} onClick={auto}>
          {busy ? "Scheduling…" : `⚡ Auto-schedule ${data.pending.length} candidate(s)`}
        </button>
      </PageHead>

      {result && (
        <div className="alert alert-success">
          <b>Scheduler result:</b>
          <ul className="plain-list">
            {result.scheduled.map((s) => <li key={s.application_id}>✓ {s.candidate} → {s.interviewer} at {fmtDateTime(s.at)}</li>)}
            {result.unscheduled.map((s) => <li key={s.application_id}>✗ {s.candidate}: {s.reason}</li>)}
          </ul>
        </div>
      )}

      <div className="grid-2 align-start">
        <Card title={`Waiting for a slot (${data.pending.length})`}>
          {data.pending.length === 0 ? <Empty title="No candidates waiting" /> : (
            <table className="table compact"><thead><tr><th>Candidate</th><th>Role</th><th>Combined</th></tr></thead>
              <tbody>{data.pending.map((a) => (
                <tr key={a.id}><td><Link to={`/admin/applications/${a.id}`}>{a.candidate_name}</Link></td><td>{a.jd_title}</td><td>{fmtNum(a.combined_score)}</td></tr>
              ))}</tbody></table>
          )}
        </Card>
        <Card title="Scheduled interviews">
          {data.interviews.length === 0 ? <Empty title="Nothing scheduled yet" /> : (
            <table className="table compact"><thead><tr><th>When</th><th>Candidate</th><th>Interviewer</th><th>Status</th></tr></thead>
              <tbody>{data.interviews.map((a) => (
                <tr key={a.id}>
                  <td className="nowrap">{fmtDateTime(a.interview_at)} {a.scheduled_by === "auto" && <Badge tone="violet">auto</Badge>}</td>
                  <td><Link to={`/admin/applications/${a.id}`}>{a.candidate_name}</Link><div className="muted small">{a.jd_title}</div></td>
                  <td>{a.interviewer_name}</td>
                  <td><StatusBadge status={a.status} />{a.interviewer_decision && <div className="small">{a.interviewer_decision}</div>}</td>
                </tr>
              ))}</tbody></table>
          )}
        </Card>
      </div>

      <Card title="Interviewer availability">
        {grid.length === 0 ? <Empty title="No availability published yet" /> : grid.map(([name, days]) => (
          <div key={name} className="avail-block">
            <h4>{name}</h4>
            <div className="avail-days">
              {Object.entries(days).map(([day, slots]) => (
                <div key={day} className="avail-day">
                  <div className="avail-date">{new Date(day).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" })}</div>
                  {slots.map((s) => (
                    <span key={s.id} className={`slot-pill ${s.is_booked ? "booked" : ""}`} title={s.is_booked ? "Booked" : "Free"}>
                      {new Date(s.start).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="legend"><span className="slot-pill">free</span><span className="slot-pill booked">booked</span></div>
      </Card>
    </>
  );
}
