import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setUnauthorizedHandler, tokenStore } from "./api";

/* ------------------------------------------------------------------ toasts */
const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message, type = "success") => {
    const id = Math.random().toString(36).slice(2);
    console.info(`[toast:${type}]`, message); // stubbed notification also goes to console
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const api = useMemo(() => ({
    success: (m) => push(m, "success"),
    error: (m) => push(m, "error"),
    info: (m) => push(m, "info"),
  }), [push]);
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>{t.message}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/* ------------------------------------------------------------------ auth */
const AuthCtx = createContext(null);
export const HOME = { admin: "/admin", interviewer: "/interviewer", candidate: "/candidate" };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(tokenStore.getUser());
  const [checking, setChecking] = useState(!!tokenStore.get());
  const navigate = useNavigate();

  const logout = useCallback(async (silent = false) => {
    if (!silent) { try { await api.post("/auth/logout"); } catch { /* ignore */ } }
    tokenStore.clear();
    setUser(null);
    navigate("/", { replace: true });
  }, [navigate]);

  // Token expired / invalid -> clear and go home
  useEffect(() => {
    setUnauthorizedHandler(() => { tokenStore.clear(); setUser(null); navigate("/", { replace: true }); });
  }, [navigate]);

  // Validate the stored token once on load
  useEffect(() => {
    if (!tokenStore.get()) return;
    api.get("/auth/me")
      .then((u) => { setUser(u); tokenStore.set(tokenStore.get(), u); })
      .catch(() => { tokenStore.clear(); setUser(null); })
      .finally(() => setChecking(false));
  }, []);

  const login = async (email, password, role) => {
    const res = await api.public("POST", "/auth/login", { email, password, role });
    tokenStore.set(res.access_token, res.user);
    setUser(res.user);
    return res.user;
  };

  return (
    <AuthCtx.Provider value={{ user, checking, login, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}
export const useAuth = () => useContext(AuthCtx);
