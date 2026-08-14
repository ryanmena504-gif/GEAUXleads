import React, { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/formatters";
import { CheckCircle2, Loader2 } from "lucide-react";

const DECISION_OPTIONS = [
  "Undecided",
  "Pursue",
  "Backburner",
  "Pass",
];

const OUTCOME_OPTIONS = [
  "Pending",
  "Contract signed",
  "Lost to competitor",
  "Homeowner canceled",
  "No response",
];

const FieldRow = ({ label, children, testId }) => (
  <div className="py-2 border-b bh-hairline last:border-b-0" data-testid={testId}>
    <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
      {label}
    </div>
    <div className="mt-1.5">{children}</div>
  </div>
);

const inputCls =
  "w-full bg-transparent border bh-hairline rounded h-9 px-2.5 text-sm text-neutral-100 focus:border-amber-500/50 outline-none";

export const EditableDecisionPanel = ({ opp, onUpdated }) => {
  const [saving, setSaving] = useState(null);
  const [local, setLocal] = useState({
    ryans_decision: opp.ryans_decision || "",
    next_follow_up: opp.next_follow_up ? opp.next_follow_up.slice(0, 10) : "",
    outcome: opp.outcome || "",
  });

  const commit = async (key, value) => {
    setSaving(key);
    try {
      const updated = await api.updateFields(opp.id, { [key]: value || null });
      onUpdated?.(updated);
      toast.success(`${key.replace(/_/g, " ")} saved`);
    } catch (e) {
      toast.error("Save failed");
    } finally {
      setSaving(null);
    }
  };

  const changeDecision = (v) => {
    setLocal((s) => ({ ...s, ryans_decision: v }));
    commit("ryans_decision", v);
  };
  const changeOutcome = (v) => {
    setLocal((s) => ({ ...s, outcome: v }));
    commit("outcome", v);
  };
  const changeFollowUp = (v) => {
    setLocal((s) => ({ ...s, next_follow_up: v }));
  };
  const submitFollowUp = () => {
    if (local.next_follow_up !== (opp.next_follow_up || "").slice(0, 10)) {
      commit("next_follow_up", local.next_follow_up);
    }
  };

  return (
    <section className="bh-surface rounded-md p-5" data-testid="decision-panel">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
            Editable
          </div>
          <h3 className="font-display text-lg font-bold text-neutral-100">
            Decision & Follow-up
          </h3>
        </div>
        {saving && (
          <span className="mono text-[10px] uppercase tracking-widest text-amber-400 inline-flex items-center gap-1">
            <Loader2 size={11} className="animate-spin" /> Saving {saving.replace(/_/g, " ")}
          </span>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-x-6">
        <FieldRow label="Ryan's decision" testId="field-ryans-decision">
          <select
            value={local.ryans_decision}
            onChange={(e) => changeDecision(e.target.value)}
            data-testid="input-ryans-decision"
            className={inputCls}
          >
            <option value="">— select —</option>
            {DECISION_OPTIONS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </FieldRow>

        <FieldRow label="Outcome" testId="field-outcome">
          <select
            value={local.outcome}
            onChange={(e) => changeOutcome(e.target.value)}
            data-testid="input-outcome"
            className={inputCls}
          >
            <option value="">— select —</option>
            {OUTCOME_OPTIONS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </FieldRow>

        <FieldRow label="Next follow-up" testId="field-next-follow-up">
          <div className="flex gap-2">
            <input
              type="date"
              value={local.next_follow_up}
              onChange={(e) => changeFollowUp(e.target.value)}
              data-testid="input-next-follow-up"
              className={inputCls + " mono"}
            />
            <button
              onClick={submitFollowUp}
              data-testid="save-next-follow-up"
              className="h-9 px-3 rounded bg-amber-500 text-neutral-950 hover:bg-amber-400 text-sm font-medium transition-colors duration-150 inline-flex items-center gap-1"
            >
              <CheckCircle2 size={13} /> Save
            </button>
          </div>
          {opp.next_follow_up && (
            <div className="mono text-[10px] text-neutral-500 mt-1">
              Currently: {fmtDate(opp.next_follow_up)}
            </div>
          )}
        </FieldRow>
      </div>
    </section>
  );
};

export default EditableDecisionPanel;
