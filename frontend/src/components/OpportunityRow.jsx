import React from "react";
import { Link } from "react-router-dom";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import StatusBadge from "@/components/StatusBadge";
import MissionBadge from "@/components/MissionBadge";
import { fmtMoneyOrStatus, sourceLabel } from "@/lib/formatters";
import { MapPin, Phone } from "lucide-react";

export const OpportunityRow = ({ opp }) => (
  <Link
    to={`/opportunities/${opp.id}`}
    data-testid={`opp-row-${opp.id}`}
    className="block bh-surface rounded-md p-4 hover:bg-white/[0.03] transition-colors duration-150"
  >
    <div className="flex items-start gap-4">
      <div className="hidden sm:flex flex-col items-center pt-1 w-14">
        <PriorityScore score={opp.priority_score} band={opp.priority_band} size="md" />
        <PriorityBand band={opp.priority_band} className="mt-1.5" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="font-display font-semibold text-neutral-100 truncate">
            {opp.name}
          </div>
          <span className="mono text-[10px] text-neutral-500">
            {opp.opportunity_id}
          </span>
        </div>

        <div className="mt-1 flex items-center gap-3 text-xs text-neutral-400 flex-wrap">
          <span className="inline-flex items-center gap-1">
            <MapPin size={12} className="text-neutral-500" />
            {opp.project_address}
          </span>
          {opp.phone && (
            <span className="inline-flex items-center gap-1 mono">
              <Phone size={11} className="text-neutral-500" />
              {opp.phone}
            </span>
          )}
        </div>

        <div className="mt-2 text-[13px] text-amber-200/90">
          <span className="text-neutral-500 mono uppercase tracking-widest text-[10px] mr-2">
            Next
          </span>
          {opp.next_best_action}
        </div>

        <div className="mt-3 flex items-center gap-1.5 flex-wrap">
          <MissionBadge mission={opp.daily_mission} size="sm" />
          <StatusBadge status={opp.status} />
          <span className="mono text-[10px] text-neutral-500 border bh-hairline rounded px-1.5 py-0.5">
            {sourceLabel(opp.source)}
          </span>
          <span className="mono text-[10px] text-neutral-500 border bh-hairline rounded px-1.5 py-0.5">
            {opp.project_type}
          </span>
        </div>
      </div>

      <div className="flex-col items-end text-right hidden md:flex">
        <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Possible work for us
        </div>
        <div className="font-display text-lg font-semibold text-neutral-100 tabular-nums">
          {fmtMoneyOrStatus(opp.estimated_value, "Not estimated yet")}
        </div>
        <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mt-2">
          Official project value
        </div>
        <div className="text-xs text-neutral-300 tabular-nums">
          {fmtMoneyOrStatus(opp.construction_value, "Not public")}
        </div>
        {opp.decision_maker && (
          <div className="text-xs text-neutral-400 mt-1 truncate max-w-[180px]">
            {opp.decision_maker}
          </div>
        )}
      </div>
    </div>
  </Link>
);

export default OpportunityRow;
