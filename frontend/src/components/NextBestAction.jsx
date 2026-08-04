import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Zap,
  CheckCircle2,
  Edit3,
  Pause,
  SkipForward,
  Ban,
  ExternalLink,
  Loader2,
  MessageSquare,
  RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import LaneBadge from "@/components/LaneBadge";
import { fmtMoney, fmtRelative } from "@/lib/formatters";

const Stat = ({ label, value }) => (
  <div>
    <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
      {label}
    </div>
    <div className="mt-0.5 text-neutral-100 font-medium truncate">
      {value ?? "—"}
    </div>
  </div>
);

export const NextBestAction = () => {
  const [state, setState] = useState({ loading: true, lead: null, note: null, queue: null });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(null);
  const [confirmDNC, setConfirmDNC] = useState(false);

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const r = await api.leadsNextBestAction();
      setState({ loading: false, lead: r.lead, note: r.note, queue: r.queue });
      setDraft(r.lead?.first_message || "");
      setEditing(false);
      setConfirmDNC(false);
    } catch {
      setState({ loading: false, lead: null, note: "Could not load next best action", queue: null });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action, extra = {}) => {
    if (!state.lead) return;
    setBusy(action);
    try {
      const res = await api.leadsAction(state.lead.id, { action, ...extra });
      toast.success(res.note || `${action.replace(/_/g, " ")} · done`);
      await load();
    } catch {
      toast.error(`Failed: ${action}`);
    } finally {
      setBusy(null);
    }
  };

  const saveMessage = async () => {
    if (!state.lead) return;
    setBusy("edit");
    try {
      await api.leadsUpdateMessage(state.lead.id, draft);
      toast.success("Message saved");
      setEditing(false);
      await load();
    } catch {
      toast.error("Save failed");
    } finally {
      setBusy(null);
    }
  };

  if (state.loading) {
    return (
      <section
        className="bh-surface rounded-lg p-6 border-t-2 border-t-amber-500/60 flex items-center gap-3 text-neutral-400"
        data-testid="nba-loading"
      >
        <Loader2 size={16} className="animate-spin text-amber-400" />
        Finding your next best action…
      </section>
    );
  }

  if (!state.lead) {
    return (
      <section
        className="bh-surface rounded-lg p-6 sm:p-8 border-t-2 border-t-amber-500/60"
        data-testid="nba-empty"
      >
        <div className="flex items-center gap-2 mb-2">
          <Zap size={13} className="text-amber-400" />
          <div className="mono text-[10px] uppercase tracking-widest text-amber-400">
            Next Best Action
          </div>
        </div>
        <div className="font-display text-2xl sm:text-3xl text-neutral-100 font-bold">
          Queue is clear.
        </div>
        <div className="text-sm text-neutral-500 mt-2 max-w-md leading-relaxed">
          {state.note || "No qualified leads waiting for action right now."}
        </div>
        <button
          onClick={load}
          data-testid="nba-reload-empty"
          className="mt-4 mono text-[10px] uppercase tracking-widest text-amber-400 hover:text-amber-300 inline-flex items-center gap-1.5"
        >
          <RefreshCw size={11} /> Reload queue
        </button>
      </section>
    );
  }

  const l = state.lead;
  const approved =
    !!l._approved_at ||
    (typeof l.approval_status === "string" &&
      l.approval_status.toLowerCase().includes("approved"));
  const timeSince = l.date_discovered || l.created_time;

  return (
    <section
      className="bh-surface rounded-lg overflow-hidden border-t-2 border-t-amber-500/60 bh-fade-in"
      data-testid="nba-card"
    >
      {/* Meta bar */}
      <div className="px-5 sm:px-7 pt-5 pb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Zap size={13} className="text-amber-400" />
            <div className="mono text-[10px] uppercase tracking-widest text-amber-400">
              Next Best Action
            </div>
            {state.queue && (
              <span className="mono text-[9px] text-neutral-500 uppercase tracking-widest">
                · {state.queue.eligible} eligible / {state.queue.total} total
              </span>
            )}
          </div>
          {l._selection_reason && (
            <div className="mono text-[10px] text-neutral-500 mt-1 truncate">
              Why this lead: {l._selection_reason}
            </div>
          )}
        </div>
        {l._airtable_url && (
          <a
            href={l._airtable_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="nba-open-full-lead"
            className="mono text-[10px] uppercase tracking-widest text-neutral-500 hover:text-amber-400 inline-flex items-center gap-1 shrink-0"
          >
            <ExternalLink size={11} /> <span className="hidden sm:inline">Open full lead</span>
          </a>
        )}
      </div>

      {/* Recommended Action — visual center */}
      <div className="px-5 sm:px-7 pb-5">
        <div
          className="font-display text-2xl sm:text-4xl lg:text-5xl font-bold text-neutral-100 leading-[1.08] tracking-tight"
          data-testid="nba-recommended-action"
        >
          {l.next_action || "Review this lead"}
        </div>
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <span className="font-display text-base sm:text-lg text-neutral-200 font-medium truncate max-w-full">
            {l.name || "Unnamed lead"}
          </span>
          <LaneBadge lane={l.lane} />
          {l.opportunity_type && (
            <span className="mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border bh-hairline text-neutral-300">
              {l.opportunity_type}
            </span>
          )}
          {approved && (
            <span
              className="mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 inline-flex items-center gap-1"
              data-testid="nba-approved-pill"
            >
              <CheckCircle2 size={10} /> Approved — awaiting messaging connection
            </span>
          )}
        </div>
      </div>

      {/* Why + AI summary */}
      {(l.why_lead_matters || l.ai_summary) && (
        <div className="px-5 sm:px-7 pb-4 border-t bh-hairline pt-4 space-y-3">
          {l.why_lead_matters && (
            <div>
              <div className="mono text-[9px] uppercase tracking-widest text-neutral-500 mb-1">
                Why this matters now
              </div>
              <div className="text-sm text-neutral-200 leading-relaxed">
                {l.why_lead_matters}
              </div>
            </div>
          )}
          {(l.ai_summary) && (
            <div>
              <div className="mono text-[9px] uppercase tracking-widest text-neutral-500 mb-1">
                AI summary
              </div>
              <div className="text-sm text-neutral-300 leading-relaxed">
                {l.ai_summary}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Compact stats row */}
      <div className="px-5 sm:px-7 pb-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-4 gap-y-3 text-sm">
        <Stat label="Lead score" value={l.lead_score} />
        <Stat label="Priority" value={l.priority} />
        <Stat label="Est. value" value={l.estimated_job_value ? fmtMoney(l.estimated_job_value) : null} />
        <Stat label="Contact conf." value={l.contact_confidence} />
        <Stat label="Source" value={l.source} />
        <Stat label="Discovered" value={timeSince ? fmtRelative(timeSince) : null} />
      </div>

      {/* Draft outbound message */}
      <div className="px-5 sm:px-7 pb-4 border-t bh-hairline pt-4">
        <div className="flex items-center justify-between mb-2">
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 inline-flex items-center gap-1.5">
            <MessageSquare size={11} /> Draft outbound message
          </div>
          {!editing && l.first_message && (
            <button
              onClick={() => setEditing(true)}
              data-testid="nba-edit-message"
              className="text-xs text-amber-400 hover:text-amber-300 inline-flex items-center gap-1"
            >
              <Edit3 size={11} /> Edit
            </button>
          )}
        </div>
        {editing ? (
          <div className="space-y-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={5}
              data-testid="nba-message-textarea"
              className="w-full bg-transparent border bh-hairline rounded px-3 py-2 text-sm text-neutral-100 focus:border-amber-500/50 outline-none font-mono leading-relaxed"
            />
            <div className="flex gap-2">
              <button
                onClick={saveMessage}
                disabled={busy === "edit"}
                data-testid="nba-save-message"
                className="h-9 px-3 rounded bg-amber-500 text-neutral-950 hover:bg-amber-400 text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1"
              >
                <CheckCircle2 size={13} /> Save message
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setDraft(l.first_message || "");
                }}
                className="h-9 px-3 rounded border bh-hairline text-neutral-300 hover:bg-white/[0.03] text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div
            className="bh-surface-2 rounded p-3 text-sm text-neutral-200 whitespace-pre-wrap leading-relaxed min-h-[60px]"
            data-testid="nba-message-view"
          >
            {l.first_message || (
              <button
                onClick={() => setEditing(true)}
                className="text-neutral-500 italic hover:text-amber-300"
              >
                No draft message yet — click to compose one.
              </button>
            )}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="px-5 sm:px-7 pb-5 pt-3 border-t bh-hairline flex flex-wrap gap-2">
        <button
          onClick={() => act("approve")}
          disabled={busy === "approve" || approved}
          data-testid="nba-approve"
          className="flex-1 min-w-[160px] h-11 rounded bg-amber-500 text-neutral-950 hover:bg-amber-400 text-sm font-semibold disabled:opacity-50 inline-flex items-center justify-center gap-2 transition-colors duration-150"
        >
          {busy === "approve" ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <CheckCircle2 size={14} />
          )}
          {approved ? "Approved" : "Approve & Send"}
        </button>
        <button
          onClick={() => act("hold")}
          disabled={busy === "hold"}
          data-testid="nba-hold"
          className="h-11 px-4 rounded border bh-hairline text-neutral-200 hover:bg-white/[0.03] text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
        >
          <Pause size={13} /> Hold
        </button>
        <button
          onClick={() => act("skip")}
          disabled={busy === "skip"}
          data-testid="nba-skip"
          className="h-11 px-4 rounded border bh-hairline text-neutral-200 hover:bg-white/[0.03] text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
        >
          <SkipForward size={13} /> Skip
        </button>
        {!confirmDNC ? (
          <button
            onClick={() => setConfirmDNC(true)}
            data-testid="nba-dnc"
            className="h-11 px-4 rounded border border-red-500/30 text-red-300 hover:bg-red-500/10 text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
          >
            <Ban size={13} /> Do Not Contact
          </button>
        ) : (
          <div className="flex items-center gap-1.5">
            <span className="mono text-[10px] uppercase tracking-widest text-red-300 mr-1">
              Confirm?
            </span>
            <button
              onClick={() => act("do_not_contact", { confirm: true })}
              disabled={busy === "do_not_contact"}
              data-testid="nba-dnc-confirm"
              className="h-11 px-3 rounded bg-red-500 text-neutral-950 hover:bg-red-400 text-sm font-semibold disabled:opacity-50"
            >
              Yes, block
            </button>
            <button
              onClick={() => setConfirmDNC(false)}
              className="h-11 px-3 rounded border bh-hairline text-sm text-neutral-300 hover:bg-white/[0.03]"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </section>
  );
};

export default NextBestAction;
