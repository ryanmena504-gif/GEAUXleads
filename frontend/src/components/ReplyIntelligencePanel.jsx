import React from "react";
import {
  MessageSquare,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  HelpCircle,
  Zap,
} from "lucide-react";

const INTENT_CONFIG = {
  estimate_request: {
    label: "Wants Estimate",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
    icon: Zap,
  },
  scheduling: {
    label: "Wants to Meet",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
    icon: ThumbsUp,
  },
  referral: {
    label: "Referral",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
    icon: HelpCircle,
  },
  not_interested: {
    label: "Not Interested",
    color: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/20",
    icon: ThumbsDown,
  },
  objection: {
    label: "Has Concerns",
    color: "text-orange-400",
    bg: "bg-orange-500/10",
    border: "border-orange-500/20",
    icon: AlertTriangle,
  },
  positive: {
    label: "Ready to Move",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
    icon: ThumbsUp,
  },
  needs_info: {
    label: "Needs Info",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
    icon: HelpCircle,
  },
  unclear: {
    label: "Unclear",
    color: "text-neutral-400",
    bg: "bg-white/[0.03]",
    border: "border-white/10",
    icon: HelpCircle,
  },
};

const URGENCY_DOT = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
};

export const ReplyIntelligencePanel = ({ classification }) => {
  if (!classification) return null;

  const { intent, urgency, suggested_action, key_phrases } = classification;
  const config = INTENT_CONFIG[intent] || INTENT_CONFIG.unclear;
  const Icon = config.icon;

  return (
    <div
      className={`rounded-md border ${config.border} ${config.bg} p-4`}
      data-testid="reply-intel"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <MessageSquare size={13} className={config.color} />
          <span
            className={`mono text-[10px] uppercase tracking-widest ${config.color}`}
          >
            What their reply means
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${URGENCY_DOT[urgency]}`} />
          <span className="mono text-[9px] uppercase tracking-widest text-neutral-500">
            {urgency} urgency
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border ${config.border} ${config.bg}`}
        >
          <Icon size={12} className={config.color} />
          <span className={`text-sm font-medium ${config.color}`}>
            {config.label}
          </span>
        </div>
      </div>

      {suggested_action && (
        <div className="mb-3">
          <div className="mono text-[9px] uppercase tracking-widest text-neutral-500 mb-1">
            Suggested Action
          </div>
          <div className="text-sm font-medium text-neutral-200">
            {suggested_action}
          </div>
        </div>
      )}

      {key_phrases && key_phrases.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {key_phrases.map((phrase, i) => (
            <span
              key={i}
              className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.05] text-neutral-400 border border-white/5"
            >
              {phrase}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export default ReplyIntelligencePanel;
