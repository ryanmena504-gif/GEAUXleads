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
      /* quiet */
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
      <div className="rounded-md p-3 bh-surface-2" data-testid="live-refresh">
        <div className="bh-eyebrow">Source · loading</div>
      </div>
    );
  }

  const isLive = status.backend === "airtable";
  const hasError = !!status.last_error;
  const isRefreshing = status.is_refreshing || manualPulse;
  const isStale = status.is_stale && !isRefreshing && !hasError;

  const label = isLive ? "New Orleans permits" : "Sample data";
  const dotColor = hasError
    ? "var(--bh-clay)"
    : isRefreshing || isStale
      ? "var(--bh-brass)"
      : "var(--bh-olive)";

  let stateLabel;
  if (hasError) {
    stateLabel = `Sync paused · click to retry`;
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
      className="w-full text-left rounded-md p-3 bh-surface-2 transition-colors duration-150 hover:bg-[var(--bh-surface-3)]/60"
    >
      <div className="flex items-center justify-between">
        <div className="bh-eyebrow">Source</div>
        <RefreshCw
          size={12}
          strokeWidth={1.75}
          className={isRefreshing ? "animate-spin" : ""}
          style={{ color: dotColor }}
        />
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[13px] text-[var(--bh-ink)]">
        <span
          className={
            "w-1.5 h-1.5 rounded-full" +
            (isRefreshing || (!isStale && !hasError) ? " bh-pulse-dot" : "")
          }
          style={{ background: dotColor }}
          data-testid="live-refresh-dot"
        />
        {label}
      </div>
      <div
        className="text-[11.5px] mt-1 text-[var(--bh-ink-mute)]"
        data-testid="live-refresh-state"
      >
        {stateLabel}
        {isLive && !isRefreshing && !isStale && !hasError && status.count !== undefined && (
          <>
            {" · "}
            <span className="text-[var(--bh-ink-3)] tabular-nums">
              {status.count} records
            </span>
          </>
        )}
      </div>
    </button>
  );
};

export default LiveRefreshIndicator;
