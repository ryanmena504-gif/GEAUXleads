import { useCallback } from "react";

/**
 * Non-blocking telemetry hook. Failures are silently swallowed —
 * navigation, exports, research, and every user action must never be
 * affected by a telemetry outage. Off by default (server env flag).
 */
const REDACT_KEY_RE = /(^|_)(email|phone|url|token|secret|key|address)($|_)/i;
const REDACT_VAL_RE = /^(pplx-|AC[A-Za-z0-9]{20,}|sk-|rsnd_)/;

const scrub = (payload) => {
  if (!payload || typeof payload !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(payload)) {
    if (REDACT_KEY_RE.test(k)) continue;
    if (typeof v === "string" && REDACT_VAL_RE.test(v)) continue;
    if (typeof v === "string" && v.length > 200) out[k] = v.slice(0, 200);
    else out[k] = v;
  }
  return out;
};

export const useTelemetry = () => {
  const track = useCallback((event, payload) => {
    try {
      const body = JSON.stringify({ event: String(event).slice(0, 80), payload: scrub(payload || {}) });
      const url =
        (process.env.REACT_APP_BACKEND_URL || "") + "/api/telemetry/event";
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      } else {
        fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => {});
      }
    } catch { /* strictly non-blocking */ }
  }, []);
  return { track };
};

export default useTelemetry;
