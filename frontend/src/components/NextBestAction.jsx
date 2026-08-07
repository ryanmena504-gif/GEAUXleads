import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Zap,
  Pause,
  SkipForward,
  Ban,
  ExternalLink,
  Loader2,
  RefreshCw,
  PenLine,
} from "lucide-react";
import { api } from "@/lib/api";
import LaneBadge from "@/components/LaneBadge";
import ContactBadge from "@/components/ContactBadge";
import DraftNoteDrawer from "@/components/DraftNoteDrawer";
import OpenInMessages from "@/components/OpenInMessages";
import { fmtMoney, fmtRelative } from "@/lib/formatters";
import { priorityLevel, priorityReason } from "@/lib/priority";

const Stat = ({ label, value }) => (
  <div>
    <div className="text-[10.5px] tracking-tight text-[var(--bh-ink-mute)]">
      {label}
    </div>
    <div className="mt-0.5 text-[var(--bh-ink)] font-medium truncate">
      {value ?? "—"}
    </div>
  </div>
);

export const NextBestAction = () => {
  const [state, setState] = useState({ loading: true, lead: null, note: null, queue: null });
  const [busy, setBusy] = useState(null);
  const [confirmDNC, setConfirmDNC] = useState(false);
  const [draftDrawerOpen, setDraftDrawerOpen] = useState(false);

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const r = await api.leadsNextBestAction();
      setState({ loading: false, lead: r.lead, note: r.note, queue: r.queue });
      setConfirmDNC(false);
    } catch {
      setState({ loading: false, lead: null, note: "Could not load your next best step", queue: null });
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
    } catch (err) {
      const reason =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        `Failed: ${action}`;
      toast.error(reason, { duration: 8000 });
    } finally {
      setBusy(null);
    }
  };

  if (state.loading) {
    return (
      <section
        className="bh-surface rounded-lg p-6 border-t-2 border-t-amber-500/60 flex items-center gap-3 text-[var(--bh-ink-mute)]"
        data-testid="nba-loading"
      >
        <Loader2 size={16} className="animate-spin text-amber-400" />
        Finding your best next step…
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
          <div className="text-[11px] tracking-tight text-amber-400">
            Today&rsquo;s top action
          </div>
        </div>
        <div className="font-display text-2xl sm:text-3xl text-[var(--bh-ink)] font-bold">
          Nothing needs you right now.
        </div>
        <div className="text-sm text-[var(--bh-ink-mute)] mt-2 max-w-md leading-relaxed">
          {state.note || "No leads are waiting on your attention today."}
        </div>
        <button
          onClick={load}
          data-testid="nba-reload-empty"
          className="mt-4 text-[11px] tracking-tight text-amber-400 hover:text-[var(--bh-brass)] inline-flex items-center gap-1.5"
        >
          <RefreshCw size={11} /> Check again
        </button>
      </section>
    );
  }

  const l = state.lead;
  const timeSince = l?.date_discovered || l?.created_time;
  const level = priorityLevel(l.priority_band, l.priority_score);
  const reason = priorityReason(l);

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
            <div className="text-[11px] tracking-tight text-amber-400">
              Today&rsquo;s top action
            </div>
            {state.queue && (
              <span className="mono text-[9px] text-[var(--bh-ink-mute)] uppercase tracking-widest">
                · {state.queue.eligible} waiting for you
              </span>
            )}
          </div>
        </div>
        {l._airtable_url && (
          <a
            href={l._airtable_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="nba-open-full-lead"
            className="text-[11px] tracking-tight text-[var(--bh-ink-mute)] hover:text-[var(--bh-brass)] inline-flex items-center gap-1 shrink-0"
          >
            <ExternalLink size={11} /> <span className="hidden sm:inline">More details</span>
          </a>
        )}
      </div>

      {/* Recommended Action — visual center */}
      <div className="px-5 sm:px-7 pb-5">
        <div
          className="font-display text-2xl sm:text-4xl lg:text-5xl font-bold text-[var(--bh-ink)] leading-[1.08] tracking-tight"
          data-testid="nba-recommended-action"
        >
          {l.next_action || "Take a look at this one"}
        </div>
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <span className="font-display text-base sm:text-lg text-[var(--bh-ink-2)] font-medium truncate max-w-full">
            {l.name || "Unnamed lead"}
          </span>
          <LaneBadge lane={l.lane} />
          {l.opportunity_type && (
            <span className="text-[11px] tracking-tight px-2 py-0.5 rounded border bh-hairline text-[var(--bh-ink-3)]">
              {l.opportunity_type}
            </span>
          )}
          <ContactBadge opportunity={l} />
        </div>
      </div>

      {/* Why this matters */}
      {(reason || l.why_lead_matters) && (
        <div className="px-5 sm:px-7 pb-4 border-t bh-hairline pt-4 space-y-3">
          <div>
            <div className="text-[10.5px] tracking-tight text-[var(--bh-ink-mute)] mb-1">
              Why this matters
            </div>
            <div className="text-sm text-[var(--bh-ink-2)] leading-relaxed">
              {reason || l.why_lead_matters}
            </div>
          </div>
        </div>
      )}

      {/* Compact stats row */}
      <div className="px-5 sm:px-7 pb-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-4 gap-y-3 text-sm">
        <Stat label="Priority" value={level || "—"} />
        <Stat label="Possible work value" value={l.estimated_job_value ? fmtMoney(l.estimated_job_value) : null} />
        <Stat label="Found on" value={l.source} />
        <Stat label="Discovered" value={timeSince ? fmtRelative(timeSince) : null} />
      </div>

      {/* Contact them — the ONLY outreach button. No approve, no send. */}
      <div className="px-5 sm:px-7 pb-4 pt-4 border-t bh-hairline">
        <OpenInMessages opportunity={l} variant="panel" />
      </div>

      {/* Action buttons */}
      <div className="px-5 sm:px-7 pb-5 pt-3 border-t bh-hairline flex flex-wrap gap-2">
        {l.lane === "partner" && (
          <button
            onClick={() => setDraftDrawerOpen(true)}
            data-testid="nba-draft-note"
            className="h-11 px-4 rounded border text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
            style={{
              background: "var(--bh-brass-mute)",
              borderColor: "var(--bh-hair-warm)",
              color: "var(--bh-brass)",
            }}
          >
            <PenLine size={13} /> Draft a note
          </button>
        )}
        <button
          onClick={() => act("hold")}
          disabled={busy === "hold"}
          data-testid="nba-hold"
          className="h-11 px-4 rounded border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)] text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
        >
          <Pause size={13} /> Save for later
        </button>
        <button
          onClick={() => act("skip")}
          disabled={busy === "skip"}
          data-testid="nba-skip"
          className="h-11 px-4 rounded border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)] text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
        >
          <SkipForward size={13} /> Skip
        </button>
        {!confirmDNC ? (
          <button
            onClick={() => setConfirmDNC(true)}
            data-testid="nba-dnc"
            className="h-11 px-4 rounded border border-red-500/30 text-red-300 hover:bg-red-500/10 text-sm inline-flex items-center gap-1.5 transition-colors duration-150"
          >
            <Ban size={13} /> Not a fit
          </button>
        ) : (
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] tracking-tight text-red-300 mr-1">
              Confirm?
            </span>
            <button
              onClick={() => act("do_not_contact", { confirm: true })}
              disabled={busy === "do_not_contact"}
              data-testid="nba-dnc-confirm"
              className="h-11 px-3 rounded bg-red-500 text-neutral-950 hover:bg-red-400 text-sm font-semibold disabled:opacity-50"
            >
              Yes, remove
            </button>
            <button
              onClick={() => setConfirmDNC(false)}
              className="h-11 px-3 rounded border bh-hairline text-sm text-[var(--bh-ink-3)] hover:bg-[var(--bh-surface-2)]"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
      {l.lane === "partner" && (
        <DraftNoteDrawer
          open={draftDrawerOpen}
          onOpenChange={setDraftDrawerOpen}
          opportunity={l}
        />
      )}
    </section>
  );
};

export default NextBestAction;
