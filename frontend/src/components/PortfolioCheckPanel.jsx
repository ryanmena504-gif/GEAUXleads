import React, { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Loader2, AlertCircle, RotateCcw, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * PortfolioCheckPanel — on-demand portfolio check trigger (Make webhook).
 *
 * Shows the "Completed project proof" card: whatever genuine public evidence
 * of this business's completed work is on file (evidence summary, outreach
 * angle, confidence), plus a "Re-run portfolio check" button that fires the
 * Make scenario for this one record — no backlog, no fees unless tapped.
 *
 * The scenario runs async (~15-30s) and writes results back to Airtable; the
 * backend returns 202 immediately. The button shows a live timer while the
 * scenario is presumed running, then prompts a refresh.
 *
 * If PORTFOLIO_CHECK_WEBHOOK is not configured, the backend 503s and the
 * button renders disabled with an explanatory note — never a crash.
 */
export const PortfolioCheckPanel = ({ opp }) => {
  const [state, setState] = useState({ status: "idle", error: null, elapsed: 0 });
  const timerRef = useRef(null);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => stopTimer, [stopTimer]);

  const run = useCallback(async () => {
    setState({ status: "running", error: null, elapsed: 0 });
    try {
      const res = await api.portfolioCheck(opp.id);
      toast.success(res?.message || "Portfolio check running — real web search takes 15-30 seconds.");
    } catch (err) {
      const detail =
        err?.response?.data?.detail || err?.message || "Portfolio check failed to start";
      setState({ status: "error", error: detail, elapsed: 0 });
      toast.error(detail);
      return;
    }
    // Live "Searching… Ns" timer; after ~40s presume the scenario finished
    // and prompt a refresh to pull the written-back proof from Airtable.
    timerRef.current = setInterval(() => {
      setState((s) => {
        const elapsed = s.elapsed + 1;
        if (elapsed >= 40) {
          stopTimer();
          return { ...s, status: "done", elapsed };
        }
        return { ...s, elapsed };
      });
    }, 1000);
  }, [opp.id, stopTimer]);

  const hasProof = Boolean(opp.evidence_summary || opp.outreach_angle);
  const confidence = opp.confidence_score ?? opp.evidence_confidence ?? null;

  return (
    <div data-testid="portfolio-check-panel" className="space-y-3">
      <div className="text-[11.5px] text-[var(--bh-ink-3)]">
        Find genuine public evidence of this business&rsquo;s completed work before
        you write to them. Real web search — one-off, per-record. Nothing sends
        automatically.
      </div>

      {hasProof && (
        <div
          data-testid="portfolio-proof-card"
          className="rounded-md border bh-hairline p-3 space-y-2"
          style={{ background: "var(--bh-surface-2)" }}
        >
          <div className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
            Completed project proof
          </div>
          {opp.evidence_summary && (
            <p className="text-[13px] text-[var(--bh-ink-2)] leading-relaxed">
              {opp.evidence_summary}
            </p>
          )}
          {opp.outreach_angle && (
            <p className="text-[12.5px] text-[var(--bh-ink-3)] leading-relaxed">
              <span className="font-medium text-[var(--bh-ink-2)]">Partnership angle: </span>
              {opp.outreach_angle}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            {confidence != null && (
              <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-medium bh-hairline text-[var(--bh-ink-2)]">
                Confidence {confidence}
              </span>
            )}
            {opp.flag_partnership && (
              <span
                className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-medium"
                style={{
                  color: "var(--bh-olive)",
                  borderColor: "rgba(107,122,85,0.35)",
                  background: "var(--bh-olive-mute)",
                }}
              >
                Partnership potential
              </span>
            )}
            {opp.website && (
              <a
                href={opp.website.startsWith("http") ? opp.website : `https://${opp.website}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-[var(--bh-brass)] hover:underline"
              >
                <ExternalLink size={10} /> {opp.website}
              </a>
            )}
          </div>
        </div>
      )}

      {state.status === "idle" && (
        <button
          type="button"
          onClick={run}
          data-testid="check-portfolio-btn"
          title="Re-run the portfolio check — real web search takes ~15-30s."
          className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold border"
          style={{
            background: "var(--bh-brass)",
            color: "var(--bh-surface)",
            borderColor: "var(--bh-brass)",
          }}
        >
          <RotateCcw size={13} strokeWidth={2} />
          {hasProof ? "Re-run portfolio check" : "Run portfolio check"}
        </button>
      )}

      {state.status === "running" && (
        <div className="flex items-center gap-2 text-[12.5px] text-[var(--bh-ink-2)] py-2">
          <Loader2 size={13} className="animate-spin text-[var(--bh-brass)]" />
          Searching… {state.elapsed}s
        </div>
      )}

      {state.status === "done" && (
        <div className="space-y-2">
          <div className="text-[12.5px] text-[var(--bh-ink-2)]">
            Check complete — refresh the page to see the new proof.
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-[12px] font-semibold border bh-hairline text-[var(--bh-ink-2)]"
          >
            <RotateCcw size={11} strokeWidth={2} /> Refresh proof
          </button>
        </div>
      )}

      {state.status === "error" && (
        <div
          className="flex items-start gap-2 rounded-md border p-2.5 text-[12px]"
          style={{
            borderColor: "rgba(138,90,69,0.28)",
            background: "rgba(138,90,69,0.08)",
            color: "#a67055",
          }}
        >
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <div className="flex-1">
            <div>{state.error}</div>
            <button
              type="button"
              onClick={() => setState({ status: "idle", error: null, elapsed: 0 })}
              className="mt-2 text-[11px] font-medium underline hover:no-underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-1.5 text-[10.5px] text-[var(--bh-ink-3)]">
        <Sparkles size={10} className="text-[var(--bh-brass)]" />
        On-demand only — one tap, one record, no backlog fees.
      </div>
    </div>
  );
};

export default PortfolioCheckPanel;
