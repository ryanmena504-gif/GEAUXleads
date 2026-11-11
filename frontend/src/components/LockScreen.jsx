import { useCallback, useEffect, useState } from "react";
import PasswordGate from "@/components/PasswordGate";
import { API } from "@/lib/api";
import { LOCK_EVENT, clearPassword, getPassword, setPassword } from "@/lib/password";

/**
 * Asks for the shared password once, then shows the app.
 * A 401 from any later request drops back to this screen.
 */
export function LockScreen({ children }) {
  const [mode, setMode] = useState("checking");
  const [message, setMessage] = useState("");

  const probe = useCallback(async (password) => {
    let res;
    try {
      res = await fetch(`${API}/config`, {
        headers: password ? { "X-App-Password": password } : {},
      });
    } catch {
      setMode("ask");
      setMessage("Can't reach the site. Check the connection and try again.");
      return;
    }
    const body = await res.json().catch(() => ({}));
    if (res.status === 503 && body.error === "password_not_configured") {
      clearPassword();
      setMode("unconfigured");
      setMessage(body.detail || "");
      return;
    }
    if (res.status === 401 || body.error === "unauthorized") {
      clearPassword();
      setMode("ask");
      setMessage(password ? "That password doesn't match the one on the server." : "");
      return;
    }
    if (!res.ok) {
      setMode("ask");
      setMessage("The site answered, but sign-in didn't go through. Try again.");
      return;
    }
    setMode("in");
    setMessage("");
  }, []);

  useEffect(() => {
    probe(getPassword());
    const onLock = (event) => {
      clearPassword();
      if (event.detail?.code === "password_not_configured") {
        setMode("unconfigured");
        setMessage("");
      } else {
        setMode("ask");
        setMessage("Sign in again.");
      }
    };
    window.addEventListener(LOCK_EVENT, onLock);
    return () => window.removeEventListener(LOCK_EVENT, onLock);
  }, [probe]);

  const submit = async (password) => {
    setPassword(password);
    await probe(password);
  };

  if (mode !== "in") {
    return <PasswordGate mode={mode} message={message} onSubmit={submit} />;
  }
  return children;
}

export default LockScreen;
