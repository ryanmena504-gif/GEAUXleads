/** The phone remembers one password. It is not a secret in the source. */

export const LOCK_EVENT = "geauxleads-lock";
const STORAGE_KEY = "geauxleads.appPassword";

export function getPassword() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setPassword(value) {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode — the sign-in still works until the tab closes */
  }
}

export function clearPassword() {
  setPassword("");
}

export function authHeaders() {
  const password = getPassword();
  return password ? { "X-App-Password": password } : {};
}

export function noteUnauthorized(status, body) {
  const code = body?.error;
  if (status === 401 || code === "unauthorized" || code === "password_not_configured") {
    clearPassword();
    window.dispatchEvent(new CustomEvent(LOCK_EVENT, { detail: { code: code || "unauthorized" } }));
    return true;
  }
  return false;
}
