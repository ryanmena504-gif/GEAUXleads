import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import { api } from "@/lib/api";
import { Flame, MessageCircleReply, CalendarClock, Trophy, ChevronRight, Inbox } from "lucide-react";
import clsx from "clsx";

const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const TouchCard = ({ touch }) => {
  const { touch: n, reached, replied, reply_rate_pct } = touch;
  return (
    <div
      data-testid={`touch-card-${n}`}
      className="bh-surface rounded p-4 flex flex-col gap-1"
    >
      <div className="text-[11px] uppercase tracking-[0.14em] text-neutral-500">
        Touch {n} of 4
      </div>
      <div className="text-2xl font-semibold text-[var(--bh-ink)]">
        {reply_rate_pct === null ? "—" : `${reply_rate_pct}%`}
      </div>
      <div className="text-xs text-[var(--bh-ink-mute)]">
        {replied} of {reached} replied
      </div>
    </div>
  );
};

const LeadRow = ({ lead, onSelect }) => (
  <button
    type="button"
    data-testid={`scoreboard-lead-${lead.id}`}
    onClick={() => onSelect(lead)}
    className="w-full text-left bh-surface rounded p-3 flex items-center gap-3 hover:bg-white/[0.03] transition-colors"
  >
    <div className="flex-1 min-w-0">
      <div className="text-sm font-medium text-[var(--bh-ink)] truncate">
        {lead.name}
      </div>
      <div className="text-xs text-[var(--bh-ink-mute)]">
        Touch {lead.touch}
        {lead.channel ? ` · ${lead.channel}` : ""}
        {lead.next_follow_up ? ` · next ${fmtDate(lead.next_follow_up)}` : ""}
      </div>
    </div>
    {lead.replied ? (
      <span className="text-[11px] px-2 py-1 rounded bg-emerald-500/15 text-emerald-300 whitespace-nowrap">
        Replied
      </span>
    ) : (
      <span className="text-[11px] px-2 py-1 rounded bg-white/[0.06] text-neutral-400 whitespace-nowrap">
        Waiting
      </span>
    )}
    {lead.estimate && (
      <span className="text-[11px] px-2 py-1 rounded bg-amber-500/15 text-amber-300 whitespace-nowrap">
        Estimate
      </span>
    )}
    <ChevronRight size={16} className="text-neutral-600 shrink-0" />
  </button>
);

const TouchHistory = ({ lead, onClose }) => (
  <div
    data-testid="touch-history-panel"
    className="fixed inset-0 z-40 flex items-end sm:items-center justify-center"
  >
    <div
      className="absolute inset-0 bg-black/60"
      onClick={onClose}
      aria-hidden="true"
    />
    <div className="relative bh-surface rounded-t-xl sm:rounded-xl p-5 w-full sm:max-w-md max-h-[85vh] overflow-y-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-[var(--bh-ink)]">
            {lead.name}
          </div>
          <div className="text-xs text-[var(--bh-ink-mute)] mt-0.5">
            Touch {lead.touch} of 4
            {lead.channel ? ` · ${lead.channel}` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-neutral-500 hover:text-neutral-200 text-xl leading-none px-2"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      <div className="mt-4 space-y-3 text-sm">
        <div className="flex justify-between gap-3">
          <span className="text-[var(--bh-ink-mute)]">Status</span>
          <span className="text-[var(--bh-ink)] font-medium">
            {lead.status || "—"}
          </span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-[var(--bh-ink-mute)]">Sent</span>
          <span className="text-[var(--bh-ink)]">
            {fmtDate(lead.message_sent_date || lead.date_contacted)}
          </span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-[var(--bh-ink-mute)]">Reply</span>
          <span className={clsx("font-medium", lead.replied ? "text-emerald-300" : "text-neutral-400")}>
            {lead.replied ? `Yes — ${fmtDate(lead.date_replied)}` : "No reply yet"}
          </span>
        </div>
        {lead.reply_summary && (
          <div className="rounded bg-white/[0.04] p-3 text-xs text-[var(--bh-ink)]">
            {lead.reply_summary}
          </div>
        )}
        <div className="flex justify-between gap-3">
          <span className="text-[var(--bh-ink-mute)]">Next follow-up</span>
          <span className="text-[var(--bh-ink)]">
            {fmtDate(lead.next_follow_up)}
          </span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-[var(--bh-ink-mute)]">Estimate</span>
          <span className={clsx("font-medium", lead.estimate ? "text-amber-300" : "text-neutral-400")}>
            {lead.estimate ? "Booked" : "Not yet"}
          </span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-[var(--bh-ink-mute)]">Job won</span>
          <span className={clsx("font-medium", lead.won ? "text-emerald-300" : "text-neutral-400")}>
            {lead.won ? "Yes" : "No"}
          </span>
        </div>
      </div>

      <Link
        to={`/opportunities/${lead.id}`}
        className="mt-5 block text-center text-sm text-amber-400 hover:text-amber-300 font-medium"
      >
        Open lead detail →
      </Link>
    </div>
  </div>
);

const WarmupScoreboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = () =>
    api
      .warmingScoreboard()
      .then((d) => {
        setData(d);
        setLoadError(null);
      })
      .catch(() => setLoadError("Could not reach the scoreboard API."))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const subtitle = loading
    ? "Loading…"
    : data?.empty
      ? "No touches logged yet"
      : `${data.touched_leads} leads in sequence · ${data.replied_leads} replied`;

  return (
    <>
      <TopHeader pageTitle="Warm-up Scoreboard" subtitle={subtitle} />

      <div className="px-4 lg:px-8 py-6 space-y-6">
        <div className="bh-surface rounded p-4 flex items-center gap-3 border-t border-t-amber-500/60">
          <Flame size={16} className="text-amber-400" />
          <div className="flex-1">
            <div className="text-sm text-[var(--bh-ink)] font-medium">
              Which touch wins replies
            </div>
            <div className="text-xs text-[var(--bh-ink-mute)]">
              Every logged touch and confirmed reply rolls up here. Replies are
              only counted when you confirm them — nothing is guessed.
            </div>
          </div>
        </div>

        {loadError && (
          <div className="bh-surface rounded-md border-t-2 border-t-red-500/60 p-4 text-sm text-red-200">
            {loadError}
          </div>
        )}

        {loading && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bh-surface rounded p-4">
                <div className="h-3 w-16 rounded bg-white/[0.06] animate-pulse" />
                <div className="mt-2 h-7 w-12 rounded bg-white/[0.06] animate-pulse" />
                <div className="mt-2 h-3 w-20 rounded bg-white/[0.04] animate-pulse" />
              </div>
            ))}
          </div>
        )}

        {!loading && !loadError && data?.empty && (
          <div
            data-testid="scoreboard-empty"
            className="bh-surface rounded p-8 text-center"
          >
            <Inbox size={28} className="mx-auto text-neutral-600" />
            <div className="mt-3 text-sm font-medium text-[var(--bh-ink)]">
              No touches logged yet
            </div>
            <div className="mt-1 text-xs text-[var(--bh-ink-mute)] max-w-sm mx-auto">
              Once you log your first touch on a lead, this board starts scoring
              reply rates per touch and tracking booked estimates.
            </div>
          </div>
        )}

        {!loading && !loadError && data && !data.empty && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {data.touches.map((t) => (
                <TouchCard key={t.touch} touch={t} />
              ))}
            </div>

            <div className="flex items-center gap-4 text-xs text-[var(--bh-ink-mute)]">
              <span className="flex items-center gap-1.5">
                <MessageCircleReply size={13} className="text-emerald-400" />
                {data.replied_leads} replied
              </span>
              <span className="flex items-center gap-1.5">
                <CalendarClock size={13} className="text-amber-400" />
                {data.estimate_leads} estimates
              </span>
              <span className="flex items-center gap-1.5">
                <Trophy size={13} className="text-amber-300" />
                {data.won_leads} won
              </span>
            </div>

            <div className="space-y-2">
              <div className="text-[11px] uppercase tracking-[0.14em] text-neutral-500">
                Leads in sequence
              </div>
              {data.leads.map((lead) => (
                <LeadRow
                  key={lead.id}
                  lead={lead}
                  onSelect={setSelected}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {selected && (
        <TouchHistory lead={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
};

export default WarmupScoreboard;
