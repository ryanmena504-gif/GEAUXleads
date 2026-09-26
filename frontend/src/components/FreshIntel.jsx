import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, Loader2, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * FreshIntel — the daily review agent's digest, surfaced on Home.
 *
 * The Make daily-review scenario scans the leads table for new info on
 * existing leads (new permits, new projects, changed contact details) and
 * flags the record with a summary. This section lists flagged leads
 * newest-first, each with a one-tap "Re-run check" that fires the portfolio
 * check webhook and clears the flag so the digest stays clean.
 *
 * Renders nothing while loading or when there is no fresh intel — the
 * section only appears when the reviewer actually found something.
 */
const FreshIntel = () => {
  const [items, setItems] = useState(null);
  const [runningId, setRunningId] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .freshIntel()
      .then((res) => {
        if (alive) setItems(res?.items || []);
      })
      .catch(() => {
        if (alive) setItems([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const rerun = useCallback(async (id) => {
    setRunningId(id);
    try {
      await api.portfolioCheck(id);
      toast.success("Portfolio check running — real web search takes 15-30 seconds.");
      setItems((prev) => (prev || []).filter((it) => it.id !== id));
    } catch (err) {
      const detail =
        err?.response?.data?.detail || err?.message || "Portfolio check failed to start";
      toast.error(detail);
    } finally {
      setRunningId(null);
    }
  }, []);

  if (!items || items.length === 0) return null;

  return (
    <section data-testid="section-fresh-intel" className="space-y-3">
      <div>
        <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1.5">
          <Sparkles size={11} strokeWidth={1.75} />
          Daily review · Fresh intel
        </div>
        <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
          New info on your leads
          <span className="ml-2 text-[13px] text-[var(--bh-ink-mute)] tabular-nums">
            ({items.length})
          </span>
        </h2>
        <p className="text-[12.5px] text-[var(--bh-ink-mute)] mt-0.5 max-w-2xl leading-relaxed">
          The daily review found something new on these leads since your last
          check. One tap re-runs the portfolio check — no backlog, no fees
          unless you tap.
        </p>
      </div>
      <div className="space-y-2">
        {items.map((it) => (
          <div
            key={it.id}
            data-testid={`fresh-intel-${it.id}`}
            className="bh-surface-2 rounded p-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <Link
                to={`/opportunities/${it.id}`}
                className="text-[13.5px] font-medium text-[var(--bh-ink)] hover:underline truncate block"
              >
                {it.name || it.company || "Unnamed lead"}
              </Link>
              {it.new_info_summary && (
                <p className="text-[12.5px] text-[var(--bh-ink-2)] mt-0.5 leading-relaxed">
                  {it.new_info_summary}
                </p>
              )}
              {it.new_info_date && (
                <p className="text-[11px] text-[var(--bh-ink-mute)] mt-1 tabular-nums">
                  Flagged {it.new_info_date}
                </p>
              )}
            </div>
            <button
              type="button"
              disabled={runningId === it.id}
              onClick={() => rerun(it.id)}
              data-testid={`fresh-intel-rerun-${it.id}`}
              title="Re-run the portfolio check for this lead"
              className="shrink-0 flex items-center gap-1.5 px-3 h-8 rounded text-[12.5px] font-medium border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)] transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {runningId === it.id ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <RotateCcw size={13} />
              )}
              {runningId === it.id ? "Running…" : "Re-run check"}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
};

export default FreshIntel;
