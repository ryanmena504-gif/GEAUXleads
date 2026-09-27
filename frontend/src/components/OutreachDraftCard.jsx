import React from "react";
import { toast } from "sonner";
import { Copy } from "lucide-react";

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

export default OutreachDraftCard;
