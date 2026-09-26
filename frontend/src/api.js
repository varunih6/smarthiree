// Thin fetch wrapper. Every request carries the JWT; a 401 logs the user out.
const BASE = import.meta.env.VITE_API_URL || "/api";
const TOKEN_KEY = "sh_token";
const USER_KEY = "sh_user";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getUser: () => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; }
  },
  set: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function request(method, path, body, { isForm = false, auth = true } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new Error("Cannot reach the server. Is the backend running on port 8000?");
  }

  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }

  if (!res.ok) {
    const msg = (data && data.detail) || `Request failed (${res.status})`;
    if (res.status === 401 && auth && token) onUnauthorized(msg);
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b = {}) => request("POST", p, b),
  put: (p, b = {}) => request("PUT", p, b),
  patch: (p, b = {}) => request("PATCH", p, b),
  del: (p) => request("DELETE", p),
  upload: (p, formData) => request("POST", p, formData, { isForm: true }),
  public: (method, p, b) => request(method, p, b, { auth: false }),
};
