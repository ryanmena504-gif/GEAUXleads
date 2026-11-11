import { useState } from "react";

/**
 * The lock screen. Shown until the phone has the same password as
 * APP_PASSWORD on the API. When that setting is missing, the steps
 * below are the whole fix — Ryan should not have to hunt through a doc.
 */
export function PasswordGate({ mode, message, onSubmit }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    const password = value.trim();
    if (!password || busy) return;
    setBusy(true);
    try {
      await onSubmit(password);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-10"
      style={{ background: "var(--bh-paper)", color: "var(--bh-ink)" }}
      data-testid="password-gate"
    >
      <div className="w-full max-w-md">
        <p className="text-[12px] tracking-[0.18em] uppercase" style={{ color: "var(--bh-brass)" }}>
          GEAUXleads
        </p>
        <h1 className="mt-2 text-[28px] leading-tight" style={{ fontFamily: "Fraunces, serif" }}>
          {mode === "unconfigured" ? "The site is locked until you set a password." : "Sign in"}
        </h1>

        {mode === "checking" && (
          <p className="mt-4 text-[15px]" style={{ color: "var(--bh-ink-3)" }} data-testid="password-checking">
            Checking the lock…
          </p>
        )}

        {mode === "unconfigured" && (
          <div className="mt-4 text-[15px] leading-relaxed" data-testid="password-setup">
            <p>{message}</p>
            <ol className="mt-4 list-decimal pl-5 space-y-2">
              <li>Open the Render dashboard.</li>
              <li>Open the API service (the one behind geauxleads.onrender.com).</li>
              <li>Go to Environment and add a variable.</li>
              <li>
                Name it <strong>APP_PASSWORD</strong>. The value is a password you make up.
                Do not leave it blank.
              </li>
              <li>Save, and wait until that service finishes redeploying.</li>
              <li>Come back to this page and type the same password.</li>
            </ol>
            <p className="mt-4" style={{ color: "var(--bh-ink-3)" }}>
              The site is up. It is refusing leads on purpose until that variable exists.
              The same steps are written in docs/RENDER_SETUP.md.
            </p>
          </div>
        )}

        {mode === "ask" && (
          <form onSubmit={submit} className="mt-6 space-y-3">
            <label className="block text-[13px]" htmlFor="app-password" style={{ color: "var(--bh-ink-3)" }}>
              Password
            </label>
            <input
              id="app-password"
              data-testid="password-input"
              type="password"
              autoComplete="current-password"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className="w-full h-12 px-3 rounded-md text-[16px]"
              style={{
                background: "var(--bh-surface)",
                border: "1px solid var(--bh-hair-strong)",
                color: "var(--bh-ink)",
              }}
            />
            {message && (
              <p className="text-[14px]" style={{ color: "var(--bh-clay)" }} data-testid="password-error">
                {message}
              </p>
            )}
            <button
              type="submit"
              data-testid="password-submit"
              disabled={busy || !value.trim()}
              className="w-full h-12 rounded-md text-[15px] font-medium disabled:opacity-50"
              style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
            >
              {busy ? "Checking…" : "Continue"}
            </button>
            <p className="text-[13px] leading-relaxed" style={{ color: "var(--bh-ink-mute)" }}>
              This phone remembers it. If the box never accepts a password, APP_PASSWORD
              is not set on the API yet. The setup steps are in docs/RENDER_SETUP.md.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

export default PasswordGate;
