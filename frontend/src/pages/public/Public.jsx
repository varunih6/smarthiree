import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { Logo } from "../../components/Layout";
import { Field, PasswordInput } from "../../components/ui";
import { HOME, useAuth } from "../../context";

const ROLES = {
  admin: { title: "Admin", sub: "Hiring Manager", icon: "🛡️", desc: "Manage jobs, screening rules, interviewers and final decisions." },
  interviewer: { title: "Interviewer", sub: "Panel member", icon: "🎙️", desc: "Set availability, view assigned candidates and submit evaluations." },
  candidate: { title: "Candidate", sub: "Job seeker", icon: "🎓", desc: "Upload your resume, apply for roles, take assessments and track status." },
};

function AuthShell({ children }) {
  return (
    <div className="auth-page">
      <div className="auth-brand">
        <Logo />
        <h2>AI-powered screening & interview tracking — one source of truth.</h2>
        <ul className="brand-points">
          <li>Resume ATS scoring against every job description</li>
          <li>Proctored online assessments with anti-cheat telemetry</li>
          <li>Availability-based interview scheduling</li>
          <li>Transparent, auditable hiring decisions</li>
        </ul>
      </div>
      <div className="auth-panel">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ landing */
export function Landing() {
  const { user } = useAuth();
  if (user) return <Navigate to={HOME[user.role]} replace />;
  return (
    <AuthShell>
      <div className="auth-card">
        <h1>Welcome</h1>
        <p className="muted">Choose how you want to sign in.</p>
        <div className="role-list">
          {Object.entries(ROLES).map(([key, r]) => (
            <Link key={key} to={`/login/${key}`} className="role-card">
              <span className="role-icon">{r.icon}</span>
              <span className="role-body">
                <span className="role-title">Login as {r.title}</span>
                <span className="role-desc">{r.desc}</span>
              </span>
              <span className="role-arrow">→</span>
            </Link>
          ))}
        </div>
        <p className="auth-foot">New candidate? <Link to="/register">Create an account</Link></p>
      </div>
    </AuthShell>
  );
}

/* ------------------------------------------------------------------ login */
export function Login() {
  const { role } = useParams();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!ROLES[role]) return <Navigate to="/" replace />;
  if (user) return <Navigate to={HOME[user.role]} replace />;
  const r = ROLES[role];

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      const u = await login(form.email.trim(), form.password, role);
      navigate(HOME[u.role], { replace: true });
    } catch (err) {
      setError(err.status === 401 ? "Invalid credentials" : err.message);
    } finally { setBusy(false); }
  };

  return (
    <AuthShell>
      <form className="auth-card" onSubmit={submit}>
        <Link to="/" className="back-link">← All login options</Link>
        <div className="login-role"><span className="role-icon">{r.icon}</span><div><h1>Login as {r.title}</h1><p className="muted">{r.sub}</p></div></div>
        {error && <div className="alert alert-error">{error}</div>}
        <Field label="Email">
          <input type="email" required autoFocus value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" />
        </Field>
        <Field label="Password">
          <PasswordInput required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="••••••••" />
        </Field>
        <div className="row-between">
          <Link to={`/reset-password/${role}`} className="small-link">Forgot password?</Link>
        </div>
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Signing in…" : "Login"}</button>
        {role === "candidate" && <p className="auth-foot">Don't have an account? <Link to="/register">Register</Link></p>}
        {role === "interviewer" && <p className="auth-foot muted">Interviewer accounts are created by the Admin.</p>}
      </form>
    </AuthShell>
  );
}

/* ------------------------------------------------------------------ register (candidate only) */
export function Register() {
  const { user } = useAuth();
  const [form, setForm] = useState({ full_name: "", email: "", mobile: "", password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={HOME[user.role]} replace />;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.password !== form.confirm_password) return setError("Passwords do not match");
    if (form.password.length < 6) return setError("Password must be at least 6 characters");
    setBusy(true);
    try {
      await api.public("POST", "/auth/register", { ...form, email: form.email.trim() });
      setDone(true); // NOT logged in automatically
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  if (done) {
    return (
      <AuthShell>
        <div className="auth-card center">
          <div className="success-icon">✓</div>
          <h1>Registration complete</h1>
          <p className="alert alert-success">Successfully registered. Please login using your email and password.</p>
          <Link to="/login/candidate" className="btn btn-primary btn-block">Login as Candidate</Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <form className="auth-card" onSubmit={submit}>
        <Link to="/" className="back-link">← Back</Link>
        <h1>Candidate registration</h1>
        <p className="muted">Create your account to apply for open roles.</p>
        {error && <div className="alert alert-error">{error}</div>}
        <Field label="Full name"><input required value={form.full_name} onChange={set("full_name")} placeholder="Sanjana Kumari" /></Field>
        <Field label="Email"><input type="email" required value={form.email} onChange={set("email")} placeholder="you@example.com" /></Field>
        <Field label="Mobile number"><input required value={form.mobile} onChange={set("mobile")} placeholder="9876543210" inputMode="tel" /></Field>
        <div className="grid-2">
          <Field label="Create password"><PasswordInput required value={form.password} onChange={set("password")} /></Field>
          <Field label="Confirm password"><PasswordInput required value={form.confirm_password} onChange={set("confirm_password")} /></Field>
        </div>
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Creating account…" : "Register"}</button>
        <p className="auth-foot">Already registered? <Link to="/login/candidate">Login as Candidate</Link></p>
      </form>
    </AuthShell>
  );
}

/* ------------------------------------------------------------------ reset password */
export function ResetPassword() {
  const { role } = useParams();
  const [form, setForm] = useState({ email: "", new_password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const r = ROLES[role] || ROLES.candidate;
  const loginPath = `/login/${ROLES[role] ? role : "candidate"}`;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.new_password !== form.confirm_password) return setError("Passwords do not match");
    setBusy(true);
    try {
      await api.public("POST", "/auth/reset-password", { ...form, email: form.email.trim(), role: ROLES[role] ? role : null });
      setDone(true); // user must log in manually
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  if (done) {
    return (
      <AuthShell>
        <div className="auth-card center">
          <div className="success-icon">✓</div>
          <h1>Password Reset Successful</h1>
          <p className="muted">Please login with your new password.</p>
          <Link to={loginPath} className="btn btn-primary btn-block">Back to {r.title} login</Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <form className="auth-card" onSubmit={submit}>
        <Link to={loginPath} className="back-link">← Back to login</Link>
        <h1>Reset password</h1>
        <p className="muted">{r.title} account</p>
        {error && <div className="alert alert-error">{error}</div>}
        <Field label="Registered email"><input type="email" required value={form.email} onChange={set("email")} /></Field>
        <Field label="New password"><PasswordInput required minLength={6} value={form.new_password} onChange={set("new_password")} /></Field>
        <Field label="Confirm new password"><PasswordInput required value={form.confirm_password} onChange={set("confirm_password")} /></Field>
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Updating…" : "Reset password"}</button>
      </form>
    </AuthShell>
  );
}
