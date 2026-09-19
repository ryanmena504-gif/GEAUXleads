import React, { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { Search, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { hasPortfolioData } from "@/components/CompletedProjectProofCard";

/**
 * CheckPortfolioButton — fires Claude/Make's Portfolio Check webhook for
 * a single lead and polls for the results. Never bulk, never automatic;
 * one explicit click per record.
 *
 * Flow:
 *   1. Click → POST /api/leads/{id}/portfolio-check (returns 202)
 *   2. Show a "Searching…" spinner for up to ~60 seconds
 *   3. Poll `getOpportunity(id)` every 5s starting at 10s
 *   4. Stop as soon as any `portfolio_*` field arrives (success)
 *   5. Bail out at 60s with a "still working" toast so the operator
 *      knows to refresh manually if Make is slow
 */
const POLL_START_MS = 10_000;
const POLL_INTERVAL_MS = 5_000;
const POLL_TIMEOUT_MS = 60_000;

export const CheckPortfolioButton = ({ opportunity, onOpportunityUpdated }) => {
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const tickerRef = useRef(null);
  const cancelledRef = useRef(false);

  useEffect(() => () => {
    // Cancel any in-flight polling when the component unmounts.
    cancelledRef.current = true;
    if (tickerRef.current) clearInterval(tickerRef.current);
  }, []);

  const alreadyChecked = hasPortfolioData(opportunity);

  const stopTicker = () => {
    if (tickerRef.current) {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
  };

  const start = async () => {
    if (busy || !opportunity?.id) return;
    setBusy(true);
    setElapsed(0);
    cancelledRef.current = false;
    try {
      await api.checkPortfolio(opportunity.id);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(detail || "Portfolio check could not start");
      setBusy(false);
      return;
    }
    toast.message("Portfolio check running — real web search takes 15-30 seconds.");
    // Tick the elapsed clock every second so the button label counts up.
    const startedAt = Date.now();
    tickerRef.current = setInterval(() => {
      if (cancelledRef.current) { stopTicker(); return; }
      setElapsed(Math.round((Date.now() - startedAt) / 1000));
    }, 1000);
    // Poll for results starting at POLL_START_MS.
    const tryFetch = async () => {
      if (cancelledRef.current) return null;
      try {
        return await api.getOpportunity(opportunity.id);
      } catch { return null; }
    };
    await new Promise((r) => setTimeout(r, POLL_START_MS));
    const deadline = startedAt + POLL_TIMEOUT_MS;
    while (Date.now() < deadline && !cancelledRef.current) {
      const fresh = await tryFetch();
      if (fresh && hasPortfolioData(fresh)) {
        stopTicker();
        setBusy(false);
        onOpportunityUpdated?.(fresh);
        toast.success("Portfolio check complete.");
        return;
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
    // Timed out — one last refetch so the operator sees whatever Make managed to write.
    const last = await tryFetch();
    stopTicker();
    setBusy(false);
    if (last) onOpportunityUpdated?.(last);
    if (last && hasPortfolioData(last)) {
      toast.success("Portfolio check complete.");
    } else {
      toast.message("Still working — refresh the page in a minute if results don't appear.");
    }
  };

  const label = busy
    ? `Searching… ${elapsed}s`
    : alreadyChecked
      ? "Re-run portfolio check"
      : "Check portfolio";
  const Icon = busy ? Loader2 : Search;

  return (
    <button
      type="button"
      onClick={start}
      disabled={busy}
      data-testid="check-portfolio-btn"
      className="inline-flex items-center gap-2 h-11 px-4 rounded-md text-[13px] font-semibold border transition-colors disabled:opacity-70 disabled:cursor-wait"
      style={{
        background: alreadyChecked ? "var(--bh-surface)" : "var(--bh-brass)",
        color: alreadyChecked ? "var(--bh-ink)" : "var(--bh-surface)",
        borderColor: alreadyChecked ? "var(--bh-hair)" : "var(--bh-brass)",
      }}
      title={
        alreadyChecked
          ? "Re-run the portfolio check — real web search takes ~15-30s."
          : "Find public evidence of this business's completed work — real web search takes ~15-30s. One-off, per-record."
      }
    >
      <Icon size={13} className={busy ? "animate-spin" : ""} strokeWidth={2} />
      {label}
    </button>
  );
};

export default CheckPortfolioButton;
