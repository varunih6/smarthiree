import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { PageHead } from "../../components/Layout";
import { BandBadge, Card, Empty, ErrorBox, Flags, ScoreBar, Spinner, StatusBadge, STATUS_LABEL, fmtNum, useFetch } from "../../components/ui";
import { useToast } from "../../context";

const COLS = [
  ["candidate_name", "Candidate"], ["resume_score", "Resume"], ["assessment_pct", "Assessment"],
  ["interview_score", "Interview"], ["combined_score", "Combined"], ["band", "Band"], ["status", "Status"],
];

export default function Pipeline() {
  const toast = useToast();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const jobs = useFetch(() => api.get("/admin/jobs"));
  const jdId = Number(params.get("jd")) || null;
  const [apps, setApps] = useState(null);
  const [batch, setBatch] = useState(null);
  const [filters, setFilters] = useState({ q: "", status: "", band: "", flagged: "" });
  const [sort, setSort] = useState({ key: "combined_score", dir: -1 });
  const poll = useRef(null);

  const loadApps = async () => {
    const qs = jdId ? `?jd_id=${jdId}` : "";
    setApps(await api.get(`/admin/applications${qs}`));
  };

  // Selecting a JD automatically triggers the LLM batch job for unscored resumes
  useEffect(() => {
    clearInterval(poll.current);
    setApps(null); setBatch(null);
    (async () => {
      try {
        if (jdId) {
          const res = await api.post(`/admin/jobs/${jdId}/batch-score`);
          if (res.status === "running") { toast.info(res.message); watchBatch(); }
        }
        await loadApps();
      } catch (e) { toast.error(e.message); }
    })();
    return () => clearInterval(poll.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jdId]);

  const watchBatch = () => {
    clearInterval(poll.current);
    poll.current = setInterval(async () => {
      const st = await api.get(`/admin/jobs/${jdId}/batch-status`);
      setBatch(st);
      if (st.status !== "running") {
        clearInterval(poll.current);
        toast.success(`Batch scoring complete: ${st.done} resume(s) scored`);
        loadApps(); jobs.reload(true);
      }
    }, 800);
  };

  const rescoreAll = async () => {
    try {
      const res = await api.post(`/admin/jobs/${jdId}/batch-score?force=true`);
      toast.info(res.message);
      if (res.status === "running") watchBatch();
    } catch (e) { toast.error(e.message); }
  };

  const rows = useMemo(() => {
    if (!apps) return [];
    let r = apps.filter((a) =>
      (!filters.q || a.candidate_name.toLowerCase().includes(filters.q.toLowerCase())) &&
      (!filters.status || a.status === filters.status) &&
      (!filters.band || a.band === filters.band) &&
      (filters.flagged === "" || (filters.flagged === "yes") === a.flags.length > 0));
    return [...r].sort((a, b) => {
      const x = a[sort.key], y = b[sort.key];
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x > y ? 1 : -1) * sort.dir;
    });
  }, [apps, filters, sort]);

  const jd = jobs.data?.find((j) => j.id === jdId);
  const shortlisted = rows.filter((r) => r.status !== "FILTERED");
  const archived = rows.filter((r) => r.status === "FILTERED");

  const Table = ({ data }) => (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {COLS.map(([k, l]) => (
              <th key={k} className="sortable" onClick={() => setSort({ key: k, dir: sort.key === k ? -sort.dir : -1 })}>
                {l} {sort.key === k ? (sort.dir === 1 ? "▲" : "▼") : ""}
              </th>
            ))}
            <th>Flags</th>{!jdId && <th>Role</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((a) => (
            <tr key={a.id} className="clickable" onClick={() => nav(`/admin/applications/${a.id}`)}>
              <td><b>{a.candidate_name}</b><div className="muted small">{a.candidate_email}</div></td>
              <td><ScoreBar value={a.resume_score} /></td>
              <td>{a.assessment_scoring === "pending" ? <span className="muted">scoring…</span> : <ScoreBar value={a.assessment_pct} />}</td>
              <td><ScoreBar value={a.interview_score} /></td>
              <td><b>{fmtNum(a.combined_score)}</b></td>
              <td><BandBadge band={a.band} /></td>
              <td><StatusBadge status={a.status} /></td>
              <td><Flags flags={a.flags} /></td>
              {!jdId && <td className="small">{a.jd_title}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <>
      <PageHead title="Candidate Pipeline" sub="Select a job description to AI-score every resume against it, then drill into any candidate.">
        {jdId && <button className="btn" onClick={rescoreAll}>↻ Re-score all resumes</button>}
      </PageHead>

      <div className="tabs">
        <button className={`tab ${!jdId ? "active" : ""}`} onClick={() => setParams({})}>All roles</button>
        {jobs.data?.map((j) => (
          <button key={j.id} className={`tab ${jdId === j.id ? "active" : ""}`} onClick={() => setParams({ jd: j.id })}>
            {j.title} <span className="tab-count">{j.applications}</span>
            {j.unscored > 0 && <span className="dot-new" title="unscored resumes" />}
          </button>
        ))}
      </div>

      {jd && (
        <div className="jd-config">
          <span>ATS threshold <b>{jd.ats_threshold}</b></span>
          <span>Weights R/A/I <b>{jd.weight_resume}/{jd.weight_assessment}/{jd.weight_interview}</b></span>
          <span>PASS ≥ <b>{jd.pass_threshold}</b> · HOLD ≥ <b>{jd.hold_threshold}</b></span>
          <span>Confidence cutoff <b>{jd.confidence_cutoff}</b></span>
        </div>
      )}

      {batch?.status === "running" && (
        <div className="alert alert-info">
          <span className="spinner" /> AI batch scoring… {batch.done}/{batch.total}
          <div className="progress"><div style={{ width: `${(batch.done / Math.max(1, batch.total)) * 100}%` }} /></div>
        </div>
      )}

      <div className="filters">
        <input placeholder="Search candidate…" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
          <option value="">All statuses</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filters.band} onChange={(e) => setFilters({ ...filters, band: e.target.value })}>
          <option value="">All bands</option><option>PASS</option><option>HOLD</option><option>REJECT</option>
        </select>
        <select value={filters.flagged} onChange={(e) => setFilters({ ...filters, flagged: e.target.value })}>
          <option value="">Flagged or not</option><option value="yes">Flagged only</option><option value="no">Not flagged</option>
        </select>
      </div>

      {jobs.error && <ErrorBox error={jobs.error} />}
      {!apps ? <Spinner /> : (
        <>
          <Card title={`Shortlist (${shortlisted.length})`}>
            {shortlisted.length ? <Table data={shortlisted} /> : <Empty title="No candidates match" />}
          </Card>
          {archived.length > 0 && (
            <Card title={`Archived below ATS threshold (${archived.length})`}>
              <div className="table-wrap">
                <table className="table compact">
                  <thead><tr><th>Candidate</th><th>Resume score</th><th>Reason</th><th /></tr></thead>
                  <tbody>
                    {archived.map((a) => (
                      <tr key={a.id} className="clickable" onClick={() => nav(`/admin/applications/${a.id}`)}>
                        <td><b>{a.candidate_name}</b></td><td><ScoreBar value={a.resume_score} /></td>
                        <td className="small">{a.archive_reason}</td><td className="link">View →</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}
