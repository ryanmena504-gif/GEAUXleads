import React from "react";
import { Link } from "react-router-dom";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import StatusBadge from "@/components/StatusBadge";
import MissionBadge from "@/components/MissionBadge";
import LaneBadge from "@/components/LaneBadge";
import { fmtMoney, sourceLabel } from "@/lib/formatters";
import { MapPin, Phone } from "lucide-react";

/**
 * Project record row — reads left→right like a builder's project book entry:
 *   fit score · project name + context · concise evidence + next move · money.
 * Reduced badge noise; spacing and typography do the ranking work.
 */
export const OpportunityRow = ({ opp }) => (
  <Link
    to={`/opportunities/${opp.id}`}
    data-testid={`opp-row-${opp.id}`}
    className="block bh-surface rounded-[12px] p-5 transition-colors duration-150 hover:bg-[var(--bh-surface-2)]/60"
  >
    <div className="flex items-start gap-5">
      <div className="hidden sm:flex flex-col items-start pt-0.5 w-[86px] shrink-0">
        <PriorityScore score={opp.priority_score} band={opp.priority_band} size="md" />
        <PriorityBand band={opp.priority_band} className="mt-2" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-3 flex-wrap">
          <div className="font-display text-[18px] text-[var(--bh-ink)] truncate tracking-tight">
            {opp.name}
          </div>
          {opp.opportunity_id && (
            <span className="text-[11px] text-[var(--bh-ink-faint)] tabular-nums">
              {opp.opportunity_id}
            </span>
          )}
        </div>

        <div className="mt-1 flex items-center gap-4 text-[12.5px] text-[var(--bh-ink-mute)] flex-wrap">
          {opp.project_address && (
            <span className="inline-flex items-center gap-1.5">
              <MapPin size={12} strokeWidth={1.75} />
              {opp.project_address}
            </span>
          )}
          {opp.phone && (
            <span className="inline-flex items-center gap-1.5 tabular-nums">
              <Phone size={11} strokeWidth={1.75} />
              {opp.phone}
            </span>
          )}
          {opp.project_type && (
            <span>· {opp.project_type}</span>
          )}
          {opp.source && (
            <span>· {sourceLabel(opp.source)}</span>
          )}
        </div>

        {opp.next_best_action && (
          <div className="mt-3 text-[14px] text-[var(--bh-ink-2)] leading-snug">
            <span className="bh-eyebrow mr-2">Next move</span>
            {opp.next_best_action}
          </div>
        )}

        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <LaneBadge lane={opp.lane} />
          <MissionBadge mission={opp.daily_mission} size="sm" />
          <StatusBadge status={opp.status} />
        </div>
      </div>

      <div className="flex-col items-end text-right hidden md:flex shrink-0">
        <div className="bh-eyebrow">Est. value</div>
        <div className="font-display text-[20px] text-[var(--bh-ink)] tabular-nums mt-0.5">
          {fmtMoney(opp.estimated_value)}
        </div>
        {opp.decision_maker && (
          <div className="text-[12px] text-[var(--bh-ink-mute)] mt-2 truncate max-w-[180px]">
            {opp.decision_maker}
          </div>
        )}
      </div>
    </div>
  </Link>
);

export default OpportunityRow;
