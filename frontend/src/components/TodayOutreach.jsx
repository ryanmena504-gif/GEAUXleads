import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Phone, Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import OpenInMessages from "@/components/OpenInMessages";
import { toast } from "sonner";

/**
 * TodayOutreach — the daily outreach queue on Home.
 *
 * Shows the top N Ready-to-Contact leads not yet contacted today (N = Ryan's
 * daily_outreach_target setting, default 10), highest governed priority
 * first, with a progress count and per-lead Email Now buttons.
 *
 * Flow per lead: tap Email Now (opens the draft in Mail) → send → tap the
 * check to mark it sent. Marking sent records message_sent_date, which drops
 * the lead from the queue and advances the progress count.
 *
 * Nothing here sends anything on its own — every send is Ryan's tap.
 */
const TodayOutreach = () => {
  const [data, setData] = useState(null);
  const [markingId, setMarkingId] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await api.outreachQueue();
      setData(res);
    } catch {
      setData({ target: 10, sent_today: 0, remaining: 0, items: [], error: true });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markSent = useCallback(
    async (id) => {
      setMarkingId(id);
      try {
        await api.recordResult(id, { event: "sent", channel: "Email" });
        toast.success("Marked sent — nice.");
        await load();
      } catch (err) {
        const detail =
          err?.response?.data?.detail || err?.message || "Couldn't mark it sent";
        toast.error(detail);
      } finally {
        setMarkingId(null);
      }
    },
    [load]
  );

  if (!data) return null;
  if (data.error) return null;

  const { target, sent_today, items } = data;
  const done = target > 0 && sent_today >= target && items.length === 0;

  return (
    <section data-testid="section-today-outreach" className="space-y-3">
      <div>
        <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1.5">
          <Phone size={11} strokeWidth={1.75} />
          Daily outreach
        </div>
        <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
          Today&apos;s outreach
          <span className="ml-2 text-[13px] text-[var(--bh-ink-mute)] tabular-nums">
            ({sent_today} of {target})
          </span>
        </h2>
        {/* Progress bar */}
        <div
          className="mt-2 h-1.5 rounded-full overflow-hidden"
          style={{ background: "var(--bh-surface)" }}
          data-testid="outreach-progress"
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${target > 0 ? Math.min(100, (sent_today / target) * 100) : 0}%`,
              background: "var(--bh-brass)",
            }}
          />
        </div>
      </div>

      {done ? (
        <p className="text-[13px] text-[var(--bh-ink-2)]" data-testid="outreach-done">
          All {target} done for today. Queue&apos;s clear.
        </p>
      ) : items.length === 0 ? (
        <p className="text-[13px] text-[var(--bh-ink-2)]" data-testid="outreach-empty">
          No ready-to-contact leads waiting right now.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <div
              key={it.id}
              data-testid={`outreach-row-${it.id}`}
              className="bh-surface-2 rounded p-3 flex items-center gap-3"
            >
              <div className="flex-1 min-w-0">
                <Link
                  to={`/opportunities/${it.id}`}
                  className="text-[13.5px] font-medium text-[var(--bh-ink)] hover:underline truncate block"
                >
                  {it.name || it.company || "Unnamed lead"}
                </Link>
                {!it.has_first_message && (
                  <p className="text-[11.5px] text-[var(--bh-ink-mute)] mt-0.5">
                    Message still writing — check back in a minute.
                  </p>
                )}
              </div>
              <OpenInMessages opportunity={it} variant="pill" />
              <button
                type="button"
                disabled={markingId === it.id}
                onClick={() => markSent(it.id)}
                data-testid={`outreach-mark-sent-${it.id}`}
                title="Mark as sent after you send the email"
                className="shrink-0 flex items-center justify-center w-8 h-8 rounded-full border bh-hairline text-emerald-300 hover:bg-emerald-500/10 transition-colors duration-150 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {markingId === it.id ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Check size={14} />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default TodayOutreach;
