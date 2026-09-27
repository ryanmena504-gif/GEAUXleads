import React, { useCallback, useState } from "react";
import { Sparkles, ExternalLink, RefreshCw, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * ResearchPanel — one-tap Perplexity research trigger.
 *
 * Usage:
 *   <ResearchPanel
 *     researchType="decision_maker"
 *     recordId={opp.id}
 *     query={`Who runs ${opp.name} at ${opp.project_address}?`}
 *     label="Who runs this?"
 *     testId={`research-dm-${opp.id}`}
 *   />
 *
 * On first click the panel POSTs to `/api/research`, streams a plain-text
 * answer + citation list into view, and caches the result in Mongo so a
 * second click returns instantly. Errors render inline with a retry, so
 * a missing key or a Perplexity 429 never crashes the surrounding page.
 * Nothing is written to Airtable — this is read-only enrichment for
 * Ryan's eyes only.
 */
export const ResearchPanel = ({
  researchType,
  recordId,
  query,
  label,
  hint,
  testId,
  onResult,
}) => {
  const [state, setState] = useState({ status: "idle", result: null, error: null });

  const run = useCallback(
    async (force = false) => {
      setState({ status: "loading", result: null, error: null });
      try {
        const result = await api.research({
          research_type: researchType,
          record_id: recordId,
          query,
          force_refresh: force,
        });
        setState({ status: "ok", result, error: null });
        if (onResult) onResult(result);
      } catch (err) {
        const status = err?.response?.status;
        const detail =
          err?.response?.data?.detail ||
          err?.message ||
          "Perplexity research failed";
        setState({ status: "error", result: null, error: { status, detail } });
        toast.error(detail);
      }
    },
    [researchType, recordId, query, onResult],
  );

  return (
    <div
      data-testid={testId || `research-${researchType}-${recordId}`}
      className="rounded-md border bh-hairline p-3 space-y-2"
      style={{ background: "var(--bh-surface-2)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Sparkles size={12} className="text-[var(--bh-brass)] shrink-0" />
            <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
              Perplexity research
            </span>
          </div>
          {hint && (
            <div className="mt-0.5 text-[11.5px] text-[var(--bh-ink-3)]">
              {hint}
            </div>
          )}
        </div>
        {state.status !== "idle" && (
          <button
            type="button"
            onClick={() => run(true)}
            data-testid={`${testId || researchType}-refetch`}
            disabled={state.status === "loading"}
            className="inline-flex items-center gap-1 text-[10.5px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] disabled:opacity-50"
            title="Force a fresh Perplexity call (bypass 7-day cache)"
          >
            <RefreshCw size={10} strokeWidth={2} /> Refetch
          </button>
        )}
      </div>

      {state.status === "idle" && (
        <button
          type="button"
          onClick={() => run(false)}
          data-testid={`${testId || researchType}-run`}
          className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold border"
          style={{
            background: "var(--bh-brass)",
            color: "var(--bh-surface)",
            borderColor: "var(--bh-brass)",
          }}
        >
          <Sparkles size={12} strokeWidth={2} /> {label}
        </button>
      )}

      {state.status === "loading" && (
        <div className="flex items-center gap-2 text-[12.5px] text-[var(--bh-ink-2)] py-2">
          <Loader2 size={13} className="animate-spin text-[var(--bh-brass)]" />
          Asking Perplexity… (usually ~5 seconds)
        </div>
      )}

      {state.status === "error" && (
        <div className="flex items-start gap-2 rounded-md border p-2.5 text-[12px]"
             style={{ borderColor: "rgba(138,90,69,0.28)", background: "rgba(138,90,69,0.08)", color: "#a67055" }}>
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <div className="flex-1">
            <div>{state.error?.detail || "Research failed"}</div>
            {state.error?.status && (
              <div className="mono text-[10px] uppercase tracking-widest mt-0.5 opacity-70">
                HTTP {state.error.status}
              </div>
            )}
            <button
              type="button"
              onClick={() => run(false)}
              className="mt-2 text-[11px] font-medium underline hover:no-underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {state.status === "ok" && state.result && (
        <div className="space-y-2">
          <div
            className="whitespace-pre-wrap text-[13px] leading-relaxed text-[var(--bh-ink-2)]"
            data-testid={`${testId || researchType}-answer`}
          >
            {state.result.answer}
          </div>
          {state.result.sources?.length > 0 && (
            <div className="pt-2 border-t bh-hairline">
              <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)] mb-1.5">
                Sources ({state.result.sources.length})
              </div>
              <ul className="space-y-1">
                {state.result.sources.slice(0, 8).map((s, i) => (
                  <li key={`${s.url}-${i}`} className="text-[12px]">
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[var(--bh-ink-2)] hover:text-[var(--bh-brass)] underline decoration-dotted underline-offset-2"
                    >
                      <ExternalLink size={9} strokeWidth={1.75} />
                      <span className="truncate max-w-[420px]">{s.title || s.url}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="text-[10px] text-[var(--bh-ink-mute)] mono tracking-widest uppercase pt-1">
            {state.result._cached ? "Cached · " : ""}
            {state.result.model || "sonar-pro"}
          </div>
        </div>
      )}
    </div>
  );
};

export default ResearchPanel;
