import React from "react";
import { CheckCircle2, Clock3, CircleX, Lightbulb } from "lucide-react";

export const PredictiveScoreBadge = ({ prediction, showDetails = false }) => {
  if (!prediction) return null;

  const {
    work_bucket,
    priority,
    why_this_matters,
    what_to_do_next,
    learning_note,
    evidence_gaps,
    feature_importance,
  } = prediction;
  const config = {
    "Contact Now": {
      color: "text-emerald-300",
      bg: "bg-emerald-500/10",
      icon: CheckCircle2,
    },
    Watch: { color: "text-amber-300", bg: "bg-amber-500/10", icon: Clock3 },
    "Not a Fit": {
      color: "text-neutral-400",
      bg: "bg-white/[0.03]",
      icon: CircleX,
    },
  }[work_bucket] || {
    color: "text-neutral-300",
    bg: "bg-white/[0.03]",
    icon: Lightbulb,
  };
  const Icon = config.icon;

  return (
    <div
      className={`rounded-md border border-white/10 ${config.bg} p-3`}
      data-testid="bloodhound-recommendation"
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={13} className={config.color} />
        <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Bloodhound recommendation
        </span>
      </div>
      <div className="flex items-baseline justify-between gap-3">
        <div className={`font-display text-lg font-bold ${config.color}`}>
          {work_bucket}
        </div>
        <div className="text-[11px] text-neutral-400">{priority} priority</div>
      </div>
      <div className="mt-3 space-y-2 text-[12px] leading-relaxed">
        <div>
          <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
            Why this matters
          </div>
          <p className="mt-0.5 text-neutral-200">{why_this_matters}</p>
        </div>
        <div>
          <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
            What to do next
          </div>
          <p className="mt-0.5 text-neutral-200">{what_to_do_next}</p>
        </div>
      </div>
      {showDetails && (
        <div className="mt-3 border-t border-white/10 pt-2 space-y-2">
          <div className="text-[11px] leading-relaxed text-neutral-400">
            {learning_note}
          </div>
          {evidence_gaps?.length > 0 && (
            <div className="text-[11px] text-amber-200/90">
              Still needed: {evidence_gaps.join(" · ")}
            </div>
          )}
          {feature_importance?.length > 0 && (
            <div className="text-[11px] text-neutral-400">
              Similar results:{" "}
              {feature_importance
                .map((item) => `${item.value} (${item.sample})`)
                .join(" · ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PredictiveScoreBadge;
