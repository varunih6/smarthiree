import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { HOME, useAuth } from "../context";
import { Spinner } from "./ui";

export function Logo({ small }) {
  return (
    <div className={`logo ${small ? "logo-sm" : ""}`}>
      <span className="logo-mark">S</span>
      <span className="logo-text">SmartHire<span className="logo-sub">Pipeline</span></span>
    </div>
  );
}

/** Blocks the route unless logged in with the right role (backend enforces too). */
export function ProtectedRoute({ role }) {
  const { user, checking } = useAuth();
  const loc = useLocation();
  if (checking) return <div className="center-page"><Spinner /></div>;
  if (!user) return <Navigate to={`/login/${role}`} replace state={{ from: loc.pathname }} />;
  if (user.role !== role) return <Navigate to={HOME[user.role]} replace />;
  return <Outlet />;
}

const NAV = {
  admin: [
    ["/admin", "Overview", "▦", true],
    ["/admin/pipeline", "Candidate Pipeline", "☰"],
    ["/admin/jobs", "Job Descriptions", "✎"],
    ["/admin/schedule", "Interview Scheduling", "◷"],
    ["/admin/interviewers", "Interviewers", "👥"],
    ["/admin/candidates", "Registered Candidates", "☺"],
    ["/admin/audit", "Audit Logs", "≡"],
  ],
  interviewer: [
    ["/interviewer", "Assigned Interviews", "☰", true],
    ["/interviewer/availability", "My Availability", "◷"],
  ],
  candidate: [
    ["/candidate", "Dashboard", "▦", true],
    ["/candidate/jobs", "Job Openings", "✎"],
  ],
};
const TITLE = { admin: "Hiring Manager", interviewer: "Interviewer", candidate: "Candidate" };

export function AppLayout({ role }) {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <Logo small />
        <div className="role-pill">{TITLE[role]} portal</div>
        <nav>
          {NAV[role].map(([to, label, icon, end]) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <span className="nav-icon">{icon}</span>{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="me">
            <div className="avatar">{user?.full_name?.[0] || "?"}</div>
            <div className="me-text"><div className="me-name">{user?.full_name}</div><div className="me-mail">{user?.email}</div></div>
          </div>
          <button className="btn btn-ghost btn-block" onClick={() => logout()}>Log out</button>
        </div>
      </aside>
      <main className="main"><Outlet /></main>
    </div>
  );
}

export const PageHead = ({ title, sub, children }) => (
  <div className="page-head">
    <div><h1>{title}</h1>{sub && <p className="muted">{sub}</p>}</div>
    {children && <div className="page-actions">{children}</div>}
  </div>
);
