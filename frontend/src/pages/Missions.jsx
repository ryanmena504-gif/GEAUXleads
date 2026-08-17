import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import MissionBadge from "@/components/MissionBadge";
import StatusBadge from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { MISSIONS } from "@/lib/constants";
import { moneyDisplay } from "@/lib/formatters";
import { CheckCircle2, Clock } from "lucide-react";

const missionCopy = {
  "Call Today":
    "Direct voice conversations still convert best. Warm and short.",
  "Send Text":
    "Fast, low-friction touch. Keep it under two sentences.",
  "Send Email":
    "Best for referrals and warm intros. Include a proof point.",
  "Research First":
    "Get one more piece of information before reaching out.",
  "Visit Property":
    "Scope-check with your eyes. Bring a business card.",
  "Prepare Estimate":
    "Match your proven template for this project type.",
  "Ask for Referral":
    "Win once, sell twice. Ask past clients who else needs work.",
  "Follow Up":
    "The most valuable follow-up. Owners buy from whoever is still present.",
  Wait:
    "Do nothing today. The signal is developing — check back Friday.",
};

const Missions = () => {
  const [grouped, setGrouped] = useState({});
  const [completed, setCompleted] = useState({});

  const load = () => api.missions().then(setGrouped);

  useEffect(() => {
    load();
  }, []);

  const total = Object.values(grouped).reduce((a, arr) => a + arr.length, 0);
  const doneCount = Object.keys(completed).length;

  const markDone = (id) => {
    setCompleted((c) => ({ ...c, [id]: true }));
    toast.success("Follow-up marked complete");
  };

  const snooze = async (id) => {
    try {
      await api.updateMission(id, "Wait");
      toast("Snoozed to Wait", { description: "You can revisit later." });
      load();
    } catch {
      toast.error("Could not snooze");
    }
  };

  return (
    <>
      <TopHeader pageTitle="Follow-Ups" subtitle={`${doneCount} of ${total} done`} />

      <div className="px-4 lg:px-8 py-6 space-y-6">
        <div className="bh-surface rounded p-4 flex items-center gap-3 border-t border-t-amber-500/60">
          <Clock size={16} className="text-amber-400" />
          <div className="flex-1">
            <div className="text-sm text-[var(--bh-ink)] font-medium">
              Today&rsquo;s plan
            </div>
            <div className="text-xs text-[var(--bh-ink-mute)]">
              Follow-ups are ranked by priority within each bucket. Take the
              high-priority ones first.
            </div>
          </div>
        </div>

        {MISSIONS.map((m) => {
          const items = grouped[m] || [];
          if (items.length === 0) return null;
          return (
            <section key={m} data-testid={`mission-section-${m}`}>
              <div className="flex items-baseline justify-between mb-3">
                <div className="flex items-center gap-3">
                  <MissionBadge mission={m} />
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
                    {items.length} opportunit{items.length === 1 ? "y" : "ies"}
                  </div>
                </div>
                <div className="hidden md:block text-xs text-[var(--bh-ink-mute)] max-w-md text-right leading-relaxed">
                  {missionCopy[m]}
                </div>
              </div>

              <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
                {items.map((o) => {
                  const done = !!completed[o.id];
                  return (
                    <div
                      key={o.id}
                      data-testid={`mission-card-${o.id}`}
                      className={
                        "bh-surface rounded p-4 flex flex-col " +
                        (done ? "opacity-40" : "")
                      }
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <PriorityScore
                            score={o.priority_score}
                            band={o.priority_band}
                            size="md"
                          />
                          <PriorityBand
                            band={o.priority_band}
                            className="mt-1"
                          />
                        </div>
                        <StatusBadge status={o.status} />
                      </div>
                      <Link
                        to={`/opportunities/${o.id}`}
                        className="mt-3 font-display font-semibold text-[var(--bh-ink)] leading-tight hover:text-amber-300"
                      >
                        {o.name}
                      </Link>
                      <div className="mt-1 text-xs text-[var(--bh-ink-mute)] truncate">
                        {o.project_address}
                      </div>
                      <div className="mt-3 text-[13px] text-amber-200/90 line-clamp-2 flex-1">
                        → {o.next_best_action}
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <span className="font-display font-semibold text-neutral-200">
                          {moneyDisplay(o) || "—"}
                        </span>
                        <span className="mono text-[10px] text-[var(--bh-ink-mute)] uppercase tracking-widest truncate max-w-[140px]">
                          {o.decision_maker || "Contact TBD"}
                        </span>
                      </div>
                      <div className="mt-3 pt-3 border-t bh-hairline flex gap-2">
                        <button
                          onClick={() => markDone(o.id)}
                          data-testid={`mission-done-${o.id}`}
                          disabled={done}
                          className="flex-1 inline-flex items-center justify-center gap-1.5 h-9 rounded bg-amber-500 text-neutral-950 hover:bg-amber-400 text-sm font-medium transition-colors duration-150 disabled:opacity-50"
                        >
                          <CheckCircle2 size={13} /> Done
                        </button>
                        <button
                          onClick={() => snooze(o.id)}
                          data-testid={`mission-snooze-${o.id}`}
                          className="h-9 px-3 rounded border bh-hairline text-neutral-300 hover:bg-white/[0.03] text-sm transition-colors duration-150"
                        >
                          Snooze
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}

        {total === 0 && (
          <div className="bh-surface rounded p-12 text-center text-[var(--bh-ink-mute)] text-sm">
            No follow-ups right now.
          </div>
        )}
      </div>
    </>
  );
};

export default Missions;
