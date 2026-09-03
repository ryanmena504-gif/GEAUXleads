import React from "react";
import { Sparkles } from "lucide-react";

/**
 * FreshContactBadge — indicator that Make just enriched this record with
 * contact info and it hasn't been viewed yet. Shown next to a row's
 * headline. Once the API sees the record again as actionable, the freshness
 * flag decays (server stops returning `is_freshly_actionable: true`).
 */
export const FreshContactBadge = ({ testId }) => (
  <span
    data-testid={testId || "fresh-contact-badge"}
    className="inline-flex items-center gap-1 rounded-full px-2 py-[1px] text-[9.5px] font-semibold uppercase tracking-widest whitespace-nowrap"
    style={{
      color: "var(--bh-surface)",
      background: "var(--bh-brass)",
      boxShadow: "0 0 0 3px rgba(178, 138, 58, 0.18)",
    }}
  >
    <Sparkles size={9} strokeWidth={2.5} />
    New contact
  </span>
);

export default FreshContactBadge;
