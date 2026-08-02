import React from "react";
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

/**
 * Explains the server's outreach verdict. The server enforces the policy; this
 * only renders its reasoning, so the panel can never disagree with what a write
 * would actually do.
 */
export const EligibilityPanel = ({ eligibility }) => {
  if (!eligibility) return null;

  const { eligible, blockers = [], warnings = [], score, score_source } = eligibility;
  if (eligible && warnings.length === 0) return null;

  const scoreNote =
    score_source === "computed_from_live_fields"
      ? "computed from live fields"
      : "from Airtable Lead score";

  return (
    <div
      className={
        "px-5 sm:px-7 py-4 border-t bh-hairline " +
        (eligible ? "bg-amber-500/[0.04]" : "bg-red-500/[0.05]")
      }
      data-testid="eligibility-panel"
    >
      <div className="flex items-center gap-2 mb-2.5">
        {eligible ? (
          <AlertTriangle size={12} className="text-amber-400" />
        ) : (
          <ShieldAlert size={12} className="text-red-400" />
        )}
        <div
          className={
            "mono text-[10px] uppercase tracking-widest " +
            (eligible ? "text-amber-300" : "text-red-300")
          }
        >
          {eligible
            ? `Approvable with ${warnings.length} warning${warnings.length === 1 ? "" : "s"}`
            : `Not approvable — ${blockers.length} blocker${blockers.length === 1 ? "" : "s"}`}
        </div>
        <span className="mono text-[9px] text-neutral-500 uppercase tracking-widest">
          · score {score} ({scoreNote})
        </span>
      </div>

      {blockers.length > 0 && (
        <ul className="space-y-1.5 mb-2" data-testid="eligibility-blockers">
          {blockers.map((b) => (
            <li key={b.code} className="text-xs leading-relaxed">
              <span className="text-red-200">{b.message}</span>
              {b.remediation && (
                <span className="text-neutral-500"> — {b.remediation}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1.5" data-testid="eligibility-warnings">
          {warnings.map((w) => (
            <li key={w.code} className="text-xs leading-relaxed">
              <span className="text-amber-200/90">{w.message}</span>
              {w.remediation && (
                <span className="text-neutral-500"> — {w.remediation}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {eligible && (
        <div className="mt-2 text-[11px] text-neutral-500 inline-flex items-center gap-1.5">
          <CheckCircle2 size={11} className="text-emerald-400" />
          Nothing blocks approval — warnings are acknowledged in the confirmation
          step.
        </div>
      )}
    </div>
  );
};

export default EligibilityPanel;
