import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { BandBadge, Card, Empty, ErrorBox, Flags, Spinner, Stat, StatusBadge, fmtDateTime, fmtNum, useFetch } from "../../components/ui";

export default function Overview() {
  const nav = useNavigate();
  const { data, loading, error } = useFetch(async () => {
    const [stats, apps, logs] = await Promise.all([
      api.get("/admin/stats"), api.get("/admin/applications"), api.get("/admin/audit-logs?limit=8"),
    ]);
    return { stats, apps, logs };
  });
  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const { stats: s, apps, logs } = data;
  const review = apps.filter((a) => a.status === "ASSESSMENT_SUBMITTED");
  const decide = apps.filter((a) => a.status === "INTERVIEW_COMPLETED");
  const pending = apps.filter((a) => a.status === "INTERVIEW_PENDING");
  const unscored = apps.filter((a) => a.status === "APPLIED");

  const ActionTable = ({ rows, empty, cta }) => rows.length === 0 ? <Empty title={empty} /> : (
    <table className="table compact">
      <thead><tr><th>Candidate</th><th>Role</th><th>Combined</th><th>Band</th><th>Flags</th><th /></tr></thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.id} className="clickable" onClick={() => nav(`/admin/applications/${a.id}`)}>
            <td><b>{a.candidate_name}</b></td><td>{a.jd_title}</td><td>{fmtNum(a.combined_score)}</td>
            <td><BandBadge band={a.band} /></td><td><Flags flags={a.flags} /></td><td className="link">{cta} →</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <>
      <PageHead title="Pipeline Dashboard" sub={`AI engine: ${s.llm_provider}`}>
        <Link to="/admin/pipeline" className="btn btn-primary">Open candidate pipeline</Link>
      </PageHead>
      <div className="stats">
        <Stat label="Total applications" value={s.total_applications} />
        <Stat label="In screening" value={s.in_screening} tone="blue" />
        <Stat label="In interview" value={s.in_interview} tone="violet" />
        <Stat label="Offers" value={s.offers} tone="green" />
        <Stat label="Flagged" value={s.flagged} tone="amber" />
        <Stat label="Registered candidates" value={s.candidates} />
      </div>

      {unscored.length > 0 && (
        <div className="alert alert-info">
          {unscored.length} application(s) have not been AI-scored yet. Open the <Link to="/admin/pipeline">pipeline</Link> and select a job to run the batch scoring.
        </div>
      )}

      <div className="grid-2">
        <Card title={`Awaiting your review after assessment (${review.length})`}>
          <ActionTable rows={review} empty="No assessments waiting" cta="Review" />
        </Card>
        <Card title={`Awaiting final decision (${decide.length})`}>
          <ActionTable rows={decide} empty="No interviews waiting for decision" cta="Decide" />
        </Card>
      </div>
      <div className="grid-2">
        <Card title={`Approved, waiting for interview slot (${pending.length})`} actions={<Link to="/admin/schedule" className="btn btn-sm">Schedule</Link>}>
          {pending.length === 0 ? <Empty title="Nobody waiting" /> : (
            <ul className="plain-list">{pending.map((a) => <li key={a.id}><Link to={`/admin/applications/${a.id}`}>{a.candidate_name}</Link> <span className="muted">· {a.jd_title}</span></li>)}</ul>
          )}
        </Card>
        <Card title="Recent activity" actions={<Link to="/admin/audit" className="btn btn-sm">All logs</Link>}>
          <ul className="activity">
            {logs.map((l) => (
              <li key={l.id}><span className="act-time">{fmtDateTime(l.created_at)}</span><b>{l.action.replaceAll("_", " ").toLowerCase()}</b> <span className="muted">{l.details}</span></li>
            ))}
          </ul>
        </Card>
      </div>
      <Card title="Status breakdown">
        <div className="chips">
          {Object.entries(s.by_status).map(([k, v]) => <span key={k} className="chip"><StatusBadge status={k} /> {v}</span>)}
        </div>
      </Card>
    </>
  );
}
