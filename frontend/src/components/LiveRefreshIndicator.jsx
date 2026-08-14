import React, { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/formatters";

const POLL_MS = 8000;

export const LiveRefreshIndicator = () => {
  const [status, setStatus] = useState(null);
  const [manualPulse, setManualPulse] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.cacheStatus();
      setStatus(s);
    } catch {
      // silent — sidebar shouldn't be noisy
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const refresh = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setManualPulse(true);
    try {
      const s = await api.refreshCache();
      setStatus(s);
      toast.success(`Refreshed — ${s.count} records`);
    } catch {
      toast.error("Refresh failed");
    } finally {
      setTimeout(() => setManualPulse(false), 800);
    }
  };

  if (!status) {
    return (
      <div className="bh-surface-2 rounded p-3" data-testid="live-refresh">
        <div className="mono text-[9px] uppercase tracking-widest text-neutral-600">
          Loading source…
        </div>
      </div>
    );
  }

  const isLive = status.backend === "airtable";
  const hasError = !!status.last_error;
  const isRefreshing = status.is_refreshing || manualPulse;
  const isStale = status.is_stale && !isRefreshing && !hasError;
  const label = isLive ? "New Orleans permits" : "Sample data";

  const dotColor = hasError
    ? "bg-red-500"
    : isRefreshing
      ? "bg-amber-400"
      : isStale
        ? "bg-amber-400"
        : "bg-emerald-400";

  let stateLabel;
  if (hasError) {
    const failures = status.consecutive_failures || 1;
    stateLabel = `Sync failed (${failures}×) · click to retry`;
  } else if (isRefreshing) {
    stateLabel = "Refreshing…";
  } else if (isStale) {
    stateLabel = "Stale · click to refresh";
  } else if (status.last_refresh) {
    stateLabel = `Updated ${fmtRelative(status.last_refresh)}`;
  } else {
    stateLabel = "Ready";
  }

  return (
    <button
      type="button"
      onClick={refresh}
      data-testid="live-refresh"
      className={
        "w-full text-left bh-surface-2 rounded p-3 hover:bg-white/[0.05] transition-colors duration-150 " +
        (hasError ? "border border-red-500/30" : "")
      }
      title={
        hasError
          ? `Airtable sync failed — ${status.last_error}`
          : isLive
            ? `Auto-refresh every ${status.ttl_seconds}s · click to refresh now`
            : "Running on sample data"
      }
    >
      <div className="flex items-center justify-between">
        <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
          Live Signal Source
        </div>
        <RefreshCw
          size={11}
          strokeWidth={2.25}
          className={
            "text-neutral-500 " +
            (isRefreshing ? "animate-spin text-amber-400" : "") +
            (hasError && !isRefreshing ? " text-red-400" : "")
          }
        />
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-xs text-neutral-200">
        <span
          className={
            "w-1.5 h-1.5 rounded-full " +
            dotColor +
            (isRefreshing || (!isStale && !hasError) ? " bh-pulse-dot" : "") +
            (hasError ? " bh-pulse-dot" : "")
          }
          data-testid="live-refresh-dot"
        />
        {label}
      </div>
      <div
        className={
          "mono text-[10px] mt-1 " +
          (hasError ? "text-red-300" : "text-neutral-500")
        }
        data-testid="live-refresh-state"
      >
        {stateLabel}
        {isLive && !isRefreshing && !isStale && !hasError && status.count !== undefined && (
          <>
            {" · "}
            <span className="text-neutral-400">{status.count} records</span>
          </>
        )}
      </div>
      {hasError && status.last_error && (
        <div
          className="mt-1.5 mono text-[9px] text-red-300/80 line-clamp-2 leading-snug"
          data-testid="live-refresh-error"
        >
          {status.last_error}
        </div>
      )}
    </button>
  );
};

export default LiveRefreshIndicator;
