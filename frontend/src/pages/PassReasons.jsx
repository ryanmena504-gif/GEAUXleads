import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ChevronRight, ExternalLink, MapPin } from "lucide-react";
import TopHeader from "@/components/TopHeader";
import { ReasonGrid, loadReasons, passWithUndo } from "@/components/PassSheet";
import { api } from "@/lib/api";
import { sourceLabel } from "@/lib/formatters";

/**
 * PassReasons — tag the backlog of disqualified leads that have no Rejection
 * reason, one card at a time. One tap saves and moves on; keys 1–8 work on a
 * keyboard. The status is already Disqualified, so only the reason and an
 * Activity Log line are written.
 */
const PassReasons = () => {
  const [data, setData] = useState(null);
  const [reasons, setReasons] = useState([]);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(0);
  const [busyKey, setBusyKey] = useState(null);

  const load = useCallback(() => {
    api
      .passBacklog()
      .then((res) => {
        setData(res);
        setIndex(0);
      })
      .catch(() => setData({ items: [], count: 0, error: true }));
  }, []);

  useEffect(() => {
    load();
    loadReasons()
      .then(setReasons)
      .catch(() => toast.error("Couldn't load reasons"));
  }, [load]);

  const items = useMemo(() => data?.items || [], [data]);
  const current = items[index];

  const pick = useCallback(
    async (reason) => {
      if (!current || busyKey) return;
      setBusyKey(reason.key);
      try {
        await passWithUndo(current, reason, "", (res) => {
          if (res === null) {
            // Undo — put the lead back in the stack.
            setDone((d) => Math.max(0, d - 1));
            load();
          }
        });
        setDone((d) => d + 1);
        setIndex((i) => i + 1);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Couldn't save that reason");
      } finally {
        setBusyKey(null);
      }
    },
    [current, busyKey, load],
  );

  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.target?.tagName === "INPUT") return;
      const n = Number(e.key);
      if (n >= 1 && n <= reasons.length) pick(reasons[n - 1]);
      if (e.key === "s" || e.key === "ArrowRight") setIndex((i) => i + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pick, reasons]);

  const total = data?.count ?? 0;
  const pct = total ? Math.min(100, (done / total) * 100) : 0;

  return (
    <>
      <TopHeader pageTitle="Tag your passes" subtitle="Teach the classifier what to stop sending" />
      <main className="px-4 lg:px-8 py-6 pb-28 max-w-2xl space-y-6">
        {data === null ? (
          <div className="text-[13px] text-[var(--bh-ink-mute)]">Loading…</div>
        ) : data.error ? (
          <div role="alert" className="bh-surface rounded-md p-4 text-[13px] text-red-300">
            Couldn't load the backlog — the GEAUXleads API didn't respond.
          </div>
        ) : !current ? (
          <section data-testid="pass-reasons-done" className="bh-ticket p-6 text-center space-y-2">
            <div className="font-display text-[26px] text-[var(--bh-ink)]">
              {done ? `${done} tagged. That's the backlog.` : "Nothing to tag."}
            </div>
            <p className="text-[13.5px] text-[var(--bh-ink-3)]">
              Every disqualified lead has a reason on file. New passes get one from the Pass button.
            </p>
            <Link to="/" className="inline-flex items-center gap-1 mt-2 text-[13px] text-[var(--bh-brass)]">
              Back to Today <ChevronRight size={13} />
            </Link>
          </section>
        ) : (
          <>
            <div className="flex items-center gap-3" data-testid="pass-reasons-progress">
              <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-[var(--bh-surface-2)]">
                <div className="h-full rounded-full transition-all duration-300" style={{ width: `${pct}%`, background: "var(--bh-brass)" }} />
              </div>
              <span className="text-[12px] tabular-nums text-[var(--bh-ink-3)] whitespace-nowrap">
                {done} of {total} tagged
              </span>
            </div>

            <article className="bh-ticket bh-ticket--hero" data-testid={`pass-card-${current.id}`}>
              <div className="px-5 pt-4 pb-4">
                <div className="mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--bh-ink-mute)]">
                  You passed on
                </div>
                <h2 className="mt-1 font-display text-[24px] leading-tight tracking-tight text-[var(--bh-ink)]">
                  {current.name || "Unnamed lead"}
                </h2>
                <div className="mt-1 text-[12.5px] text-[var(--bh-ink-mute)] flex flex-wrap gap-x-2">
                  {current.project_address && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin size={11} /> {current.project_address}
                    </span>
                  )}
                  {current.project_type && <span>· {current.project_type}</span>}
                  {current.source && <span>· {sourceLabel(current.source)}</span>}
                </div>
              </div>
              {(current.permit_description || current.priority_explanation || current.current_recommendation) && (
                <>
                  <div className="bh-perforation" aria-hidden="true" />
                  <p className="px-5 py-4 text-[13.5px] leading-relaxed text-[var(--bh-ink-2)] line-clamp-5">
                    {current.permit_description || current.priority_explanation || current.current_recommendation}
                  </p>
                </>
              )}
              <div className="px-5 pb-4 flex items-center gap-3 text-[12px]">
                {current.source_url && (
                  <a
                    href={current.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
                  >
                    <ExternalLink size={12} /> Source
                  </a>
                )}
                <Link to={`/opportunities/${current.id}`} className="text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]">
                  Open record
                </Link>
                <button
                  type="button"
                  onClick={() => setIndex((i) => i + 1)}
                  data-testid="pass-reasons-skip"
                  className="ml-auto text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
                >
                  Skip for now
                </button>
              </div>
            </article>

            <div>
              <div className="mb-2 text-[12.5px] text-[var(--bh-ink-3)]">Why did you pass?</div>
              <ReasonGrid reasons={reasons} busyKey={busyKey} onPick={pick} />
              <p className="hidden lg:block mt-2 text-[11.5px] text-[var(--bh-ink-mute)]">
                Keyboard: 1–{reasons.length} picks a reason, S skips.
              </p>
            </div>
          </>
        )}
      </main>
    </>
  );
};

export default PassReasons;
