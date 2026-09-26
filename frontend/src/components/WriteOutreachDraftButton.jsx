import React, { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { PenLine, Loader2, Copy } from "lucide-react";
import { api } from "@/lib/api";

/**
 * WriteOutreachDraftButton — fires Claude/Make's Outreach Writer webhook for
 * a single lead, then polls until a new `Draft Outreach Body` lands on the
 * record. Mirrors CheckPortfolioButton. One explicit click per record; the
 * draft is shown for Ryan to review and send himself — nothing sends.
 */
const POLL_START_MS = 5_000;
const POLL_INTERVAL_MS = 5_000;
const POLL_TIMEOUT_MS = 60_000;

const draftStamp = (opp) =>
  `${opp?.draft_outreach_generated_at || ""}|${opp?.draft_outreach_body || ""}`;

export const WriteOutreachDraftButton = ({ opportunity, onOpportunityUpdated }) => {
  const [busy, setBusy] = useState(false);
  const cancelledRef = useRef(false);

  useEffect(() => () => { cancelledRef.current = true; }, []);

  const hasDraft = Boolean(opportunity?.draft_outreach_body);

  const start = async () => {
    if (busy || !opportunity?.id) return;
    setBusy(true);
    cancelledRef.current = false;
    const before = draftStamp(opportunity);
    try {
      await api.writeOutreachDraft(opportunity.id);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(detail || "Outreach draft could not start");
      setBusy(false);
      return;
    }
    const tryFetch = async () => {
      if (cancelledRef.current) return null;
      try {
        return await api.getOpportunity(opportunity.id);
      } catch { return null; }
    };
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    await new Promise((r) => setTimeout(r, POLL_START_MS));
    while (Date.now() < deadline && !cancelledRef.current) {
      const fresh = await tryFetch();
      if (fresh && fresh.draft_outreach_body && draftStamp(fresh) !== before) {
        setBusy(false);
        onOpportunityUpdated?.(fresh);
        toast.success("Draft ready — review it below. Nothing was sent.");
        return;
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
    const last = await tryFetch();
    setBusy(false);
    if (last) onOpportunityUpdated?.(last);
    if (last && last.draft_outreach_body && draftStamp(last) !== before) {
      toast.success("Draft ready — review it below. Nothing was sent.");
    } else {
      toast.message("Still working — refresh the page in a minute if the draft doesn't appear.");
    }
  };

  const Icon = busy ? Loader2 : PenLine;
  return (
    <button
      type="button"
      onClick={start}
      disabled={busy}
      data-testid="write-outreach-draft-btn"
      className="inline-flex items-center gap-2 h-11 px-4 rounded-md text-[13px] font-semibold border transition-colors disabled:opacity-70 disabled:cursor-wait"
      style={{
        background: "var(--bh-surface)",
        color: "var(--bh-ink)",
        borderColor: "var(--bh-hair)",
      }}
      title="Ask the Outreach Writer agent for a draft. You review it and send it yourself."
    >
      <Icon size={13} className={busy ? "animate-spin" : ""} strokeWidth={2} />
      {busy ? "Working…" : hasDraft ? "Rewrite outreach draft" : "Write outreach draft"}
    </button>
  );
};

/** Read-only view of the agent's latest draft. Hidden when there is none. */
export const OutreachDraftCard = ({ opportunity }) => {
  const subject = opportunity?.draft_outreach_subject;
  const body = opportunity?.draft_outreach_body;
  if (!body) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(subject ? `${subject}\n\n${body}` : body);
      toast.success("Draft copied");
    } catch {
      toast.error("Couldn't copy — select the text instead");
    }
  };

  return (
    <section className="bh-surface rounded-md p-5" data-testid="outreach-draft-card">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
          Outreach draft · not sent
        </div>
        <button
          type="button"
          onClick={copy}
          data-testid="outreach-draft-copy"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--bh-ink-3)] hover:text-[var(--bh-brass)]"
        >
          <Copy size={11} strokeWidth={1.75} /> Copy
        </button>
      </div>
      {subject && (
        <div className="text-[13px] font-semibold text-[var(--bh-ink)] mb-2">{subject}</div>
      )}
      <div className="text-[13px] text-[var(--bh-ink-2)] whitespace-pre-wrap leading-relaxed">{body}</div>
      {opportunity?.draft_outreach_generated_at && (
        <div className="mt-3 text-[11px] text-[var(--bh-ink-mute)]">
          Written {new Date(opportunity.draft_outreach_generated_at).toLocaleString()}
        </div>
      )}
    </section>
  );
};

export default WriteOutreachDraftButton;
