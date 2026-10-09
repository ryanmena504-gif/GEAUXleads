import React, { useCallback, useEffect, useRef, useState } from "react";
import { PenLine, Loader2, AlertCircle, MessageSquare, Check, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * OutreachWriterButton — direct draft generation with transparency.
 *
 * Tapping fires the backend, which builds the prompt from the lead, calls
 * OpenAI, and returns the draft + full recipe immediately. No Make webhook,
 * no polling, no "refresh the page".
 *
 * Shows the draft inline with a collapsible recipe (what the AI was told +
 * which lead fields were used), an "Open in messages" sms: link, and a
 * one-tap "Logged as sent" button.
 */
export const OutreachWriterButton = ({ opp }) => {
  const [state, setState] = useState({ status: "idle", error: null, draft: null, recipe: null });
  const [showRecipe, setShowRecipe] = useState(false);
  const [logged, setLogged] = useState(false);

  const run = useCallback(async () => {
    setState({ status: "running", error: null, draft: null, recipe: null });
    setShowRecipe(false);
    setLogged(false);
    try {
      const res = await api.outreachWrite(opp.id);
      setState({ status: "ready", error: null, draft: res.draft, recipe: res.recipe });
      toast.success("Draft ready.");
    } catch (err) {
      const detail =
        err?.response?.data?.detail || err?.message || "Draft generation failed";
      setState({ status: "error", error: detail, draft: null, recipe: null });
      toast.error(detail);
    }
  }, [opp.id]);

  const markSent = useCallback(async () => {
    try {
      await api.recordResult(opp.id, { result: "sent", note: "Sent via transparent outreach flow" });
      setLogged(true);
      toast.success("Logged as sent.");
    } catch (err) {
      toast.error("Could not log — the text itself is unaffected.");
    }
  }, [opp.id]);

  const hasMessage = Boolean(opp.first_message || opp.first_contact_message);
  const smsHref = state.draft && opp.phone
    ? `sms:${opp.phone}?body=${encodeURIComponent(state.draft)}`
    : null;

  if (state.status === "running") {
    return (
      <div className="flex items-center gap-2 text-[12.5px] text-[var(--bh-ink-2)] py-1.5">
        <Loader2 size={13} className="animate-spin text-[var(--bh-brass)]" />
        Writing your draft…
      </div>
    );
  }

  if (state.status === "ready" && state.draft) {
    return (
      <div className="space-y-2.5 rounded-md border bh-hairline p-3 bg-[var(--bh-surface)]">
        <div className="text-[12.5px] leading-relaxed text-[var(--bh-ink)] whitespace-pre-wrap">
          {state.draft}
        </div>

        <button
          type="button"
          onClick={() => setShowRecipe((v) => !v)}
          className="flex items-center gap-1 text-[11px] font-medium text-[var(--bh-ink-3)] hover:text-[var(--bh-ink-2)]"
        >
          <ChevronDown size={12} className={showRecipe ? "rotate-180" : ""} />
          {showRecipe ? "Hide what the AI was told" : "See what the AI was told"}
        </button>

        {showRecipe && state.recipe && (
          <div className="rounded bg-[var(--bh-surface-2)] p-2.5 text-[11px] leading-relaxed text-[var(--bh-ink-3)] space-y-2 max-h-64 overflow-y-auto">
            <div>
              <div className="font-semibold text-[var(--bh-ink-2)] mb-1">Instructions given</div>
              <div className="whitespace-pre-wrap">{state.recipe.system_prompt}</div>
            </div>
            <div>
              <div className="font-semibold text-[var(--bh-ink-2)] mb-1">Lead info used</div>
              {Object.entries(state.recipe.inputs_used || {}).map(([k, v]) => (
                <div key={k}>
                  <span className="font-medium">{k.replace(/_/g, " ")}:</span> {String(v).slice(0, 120)}
                </div>
              ))}
            </div>
            <div className="text-[10px] opacity-70">Model: {state.recipe.model}</div>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          {smsHref && (
            <a
              href={smsHref}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 h-9 rounded text-sm font-medium bg-[var(--bh-brass)] text-white hover:opacity-90"
            >
              <MessageSquare size={14} />
              Open in messages
            </a>
          )}
          <button
            type="button"
            onClick={markSent}
            disabled={logged}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 h-9 rounded text-sm border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)] disabled:opacity-60"
          >
            <Check size={14} />
            {logged ? "Logged" : "Logged as sent"}
          </button>
        </div>

        <button
          type="button"
          onClick={run}
          className="text-[11px] font-medium underline hover:no-underline text-[var(--bh-ink-3)]"
        >
          Re-write
        </button>
      </div>
    );
  }

  if (state.status === "error") {
    return (
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
            onClick={() => setState({ status: "idle", error: null, draft: null, recipe: null })}
            className="mt-2 text-[11px] font-medium underline hover:no-underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={run}
      data-testid="write-outreach-btn"
      title="Write the outreach message for this lead — direct, with full transparency."
      className="w-full flex items-center gap-2 px-3 h-9 rounded text-sm border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)] transition-colors duration-150"
    >
      <PenLine size={14} />
      {hasMessage ? "Re-write outreach" : "Write outreach"}
    </button>
  );
};

export default OutreachWriterButton;
