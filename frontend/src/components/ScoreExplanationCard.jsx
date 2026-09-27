import React from "react";
import { ShieldCheck, Info } from "lucide-react";

/**
 * Displays the governed score/priority fields verbatim from Airtable+Claude.
 * Never recomputes anything. Every field has a provenance chip so operator
 * knows exactly which system owns each value.
 */
const PROV_STYLES = {
  claude: { label: "Claude", color: "#8a6a3f", bg: "rgba(191,150,90,0.14)" },
  source: { label: "Source", color: "#3f6b6b", bg: "rgba(63,107,107,0.12)" },
  enrichment: { label: "Enrichment", color: "#5b7a4a", bg: "rgba(91,122,74,0.12)" },
  bloodhound: { label: "GEAUXleads UI", color: "#6a5a8a", bg: "rgba(106,90,138,0.12)" },
};

const Prov = ({ kind }) => {
  const s = PROV_STYLES[kind] || PROV_STYLES.claude;
  return (
    <span
      className="mono uppercase tracking-widest text-[9px] px-1.5 py-[1px] rounded-sm"
      style={{ color: s.color, background: s.bg }}
    >
      {s.label}
    </span>
  );
};

const Field = ({ label, value, prov, testId }) => (
  <div className="flex flex-col gap-0.5" data-testid={testId}>
    <div className="flex items-center gap-1.5">
      <span className="text-[10.5px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
        {label}
      </span>
      <Prov kind={prov} />
    </div>
    <div className="text-[13px] text-[var(--bh-ink)] tabular-nums">
      {value != null && value !== "" ? (
        String(value)
      ) : (
        <span className="text-[var(--bh-ink-3)] italic">Not yet classified</span>
      )}
    </div>
  </div>
);

export const ScoreExplanationCard = ({ opp, testId = "score-explanation" }) => {
  if (!opp) return null;
  return (
    <section
      data-testid={testId}
      className="rounded-md border bh-hairline p-4"
      style={{ background: "var(--bh-surface-2)" }}
    >
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck size={13} className="text-[var(--bh-brass)]" />
        <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
          Why this priority
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Field
          label="Governed Priority Score"
          value={opp.governed_priority_score}
          prov="claude"
          testId={`${testId}-gps`}
        />
        <Field label="Current Queue" value={opp.current_queue} prov="claude" />
        <Field label="Contact Readiness" value={opp.contact_readiness} prov="claude" />
        <Field label="Money Signal" value={opp.money_signal} prov="claude" />
        <Field label="Contact State" value={opp.contact_state} prov="claude" />
        <Field label="Freshness" value={opp.freshness} prov="claude" />
      </div>
      {opp.priority_explanation && (
        <div className="mt-4 pt-3 border-t bh-hairline">
          <div className="flex items-center gap-1.5 mb-1">
            <Info size={11} className="text-[var(--bh-brass)]" />
            <span className="mono uppercase tracking-widest text-[9.5px] text-[var(--bh-ink-mute)]">
              Priority explanation
            </span>
            <Prov kind="claude" />
          </div>
          <div className="text-[12.5px] leading-relaxed text-[var(--bh-ink-2)]">
            {opp.priority_explanation}
          </div>
        </div>
      )}
      {opp.score_basis && (
        <div className="mt-3">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="mono uppercase tracking-widest text-[9.5px] text-[var(--bh-ink-mute)]">
              Score basis
            </span>
            <Prov kind="claude" />
          </div>
          <div className="text-[12.5px] leading-relaxed text-[var(--bh-ink-2)]">
            {opp.score_basis}
          </div>
        </div>
      )}
    </section>
  );
};

export default ScoreExplanationCard;
