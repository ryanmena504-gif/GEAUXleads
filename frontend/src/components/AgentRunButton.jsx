import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";

/**
 * AgentRunButton — one tap fires an on-demand Make agent for a single lead,
 * then re-reads the record (fresh from Airtable) until one of `watchFields`
 * changes, and hands the updated record back via `onUpdated`.
 *
 * The agent only writes research back to Airtable — nothing is ever sent to
 * the lead. When the backend webhook env var is missing it 503s and the
 * error is shown inline; never a crash.
 */
const POLL_START_MS = 8_000;
const POLL_INTERVAL_MS = 5_000;
const POLL_TIMEOUT_MS = 90_000;

const stamp = (opp, fields) => JSON.stringify(fields.map((f) => opp?.[f] ?? null));

export const AgentRunButton = ({
  opp,
  trigger, // (id) => Promise
  watchFields,
  label,
  icon: Icon,
  doneMessage,
  onUpdated,
  testId,
}) => {
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const cancelled = useRef(false);

  useEffect(() => () => { cancelled.current = true; }, []);

  const run = async () => {
    if (busy || !opp?.id) return;
    setBusy(true);
    setError(null);
    setElapsed(0);
    cancelled.current = false;
    const before = stamp(opp, watchFields);
    try {
      await trigger(opp.id);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || `${label} failed to start`;
      setError(detail);
      toast.error(detail);
      setBusy(false);
      return;
    }
    const started = Date.now();
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    const fetchFresh = async () => {
      try { return await api.getOpportunity(opp.id, { fresh: true }); } catch { return null; }
    };
    await new Promise((r) => setTimeout(r, POLL_START_MS));
    let latest = null;
    while (!cancelled.current && Date.now() - started < POLL_TIMEOUT_MS) {
      latest = await fetchFresh();
      if (latest && stamp(latest, watchFields) !== before) break;
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
    clearInterval(tick);
    if (cancelled.current) return;
    setBusy(false);
    if (latest) onUpdated?.(latest);
    if (latest && stamp(latest, watchFields) !== before) {
      toast.success(doneMessage);
    } else {
      toast.message("Still working — refresh in a minute if nothing changes.");
    }
  };

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={run}
        disabled={busy}
        data-testid={testId}
        className="inline-flex items-center gap-2 h-10 px-4 rounded-md text-[13px] font-semibold border transition-colors disabled:opacity-70 disabled:cursor-wait"
        style={{ background: "var(--bh-surface)", color: "var(--bh-ink)", borderColor: "var(--bh-hair)" }}
      >
        {busy ? <Loader2 size={13} className="animate-spin" /> : Icon ? <Icon size={13} strokeWidth={2} /> : null}
        {busy ? `Working… ${elapsed}s` : label}
      </button>
      {error && (
        <div className="text-[11.5px] text-red-300" role="alert">{error}</div>
      )}
    </div>
  );
};

export default AgentRunButton;
