import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Clock3, MessageSquare, Mail, FileText, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import OpenInMessages from "@/components/OpenInMessages";

/**
 * TimeToNudge — the "you already touched these, keep going" strip.
 *
 * The single highest ROI thing Ryan can do each day is come back to a lead
 * he already contacted. Bloodhound remembers every Text/Email tap via the
 * handoff logger; this component surfaces the ones that have gone quiet.
 *
 * Buckets are ranked so estimate check-ins come first (real money on the
 * line), then text nudges (fastest), then email nudges. Each row keeps the
 * native handoff so tapping Contact them opens the same iPhone/Gmail draft
 * flow used elsewhere — approval-only.
 */
const BUCKET_META = {
  estimate_check: {
    label: "Check on estimate",
    hint: "You sent an estimate — see if they're ready",
    icon: FileText,
    fg: "var(--bh-brass)",
    bg: "var(--bh-brass-mute)",
    border: "var(--bh-hair-warm)",
  },
  text_nudge: {
    label: "Nudge by text",
    hint: "You texted, no reply — send a short check-in",
    icon: MessageSquare,
    fg: "var(--bh-olive)",
    bg: "var(--bh-olive-mute)",
    border: "rgba(107,122,85,0.32)",
  },
  email_nudge: {
    label: "Nudge by email",
    hint: "You emailed, no reply — send a friendly follow-up",
    icon: Mail,
    fg: "#4b6b6f",
    bg: "rgba(75,107,111,0.10)",
    border: "rgba(75,107,111,0.30)",
  },
};

const NudgeRow = ({ item }) => {
  const meta = BUCKET_META[item.bucket] || BUCKET_META.text_nudge;
  const Icon = meta.icon;
  const opp = item.opportunity || {};
  const days = Math.max(0, Math.round(item.last_touch?.days_ago ?? 0));
  return (
    <div
      className="bh-surface rounded-md p-4 flex items-start gap-4 hover:bg-white/[0.03] transition-colors duration-150"
      data-testid={`nudge-row-${opp.id}`}
    >
      <div
        className="w-9 h-9 shrink-0 rounded-full flex items-center justify-center"
        style={{ background: meta.bg, border: `1px solid ${meta.border}` }}
      >
        <Icon size={15} strokeWidth={1.75} style={{ color: meta.fg }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-[10.5px] px-2 py-0.5 rounded-full border font-medium tracking-tight"
            style={{ background: meta.bg, borderColor: meta.border, color: meta.fg }}
          >
            {meta.label}
          </span>
          <Link
            to={`/opportunities/${opp.id}`}
            data-testid={`nudge-open-${opp.id}`}
            className="font-display font-semibold text-[var(--bh-ink)] hover:text-[var(--bh-brass)] truncate"
          >
            {opp.name || "Unnamed lead"}
          </Link>
        </div>
        <div className="mt-1 text-[12.5px] text-[var(--bh-ink-mute)] inline-flex items-center gap-1.5">
          <Clock3 size={11} strokeWidth={1.75} />
          {days === 0 ? "Today" : days === 1 ? "1 day ago" : `${days} days ago`} · {meta.hint}
        </div>
        <div className="mt-3">
          <OpenInMessages opportunity={opp} variant="pill" />
        </div>
      </div>
      <Link
        to={`/opportunities/${opp.id}`}
        className="hidden sm:inline-flex items-center text-[var(--bh-ink-mute)] hover:text-[var(--bh-brass)] mt-1"
        aria-label="Open"
      >
        <ChevronRight size={16} strokeWidth={1.75} />
      </Link>
    </div>
  );
};

export const TimeToNudge = () => {
  const [state, setState] = useState({ loading: true, items: [] });
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let mounted = true;
    api
      .dueFollowUps(20)
      .then((r) => {
        if (!mounted) return;
        setState({ loading: false, items: r.items || [] });
      })
      .catch(() => mounted && setState({ loading: false, items: [] }));
    return () => {
      mounted = false;
    };
  }, []);

  if (state.loading) return null;
  if (!state.items.length) return null;

  const shown = collapsed ? state.items.slice(0, 3) : state.items.slice(0, 8);
  const hiddenCount = state.items.length - shown.length;

  return (
    <section
      className="space-y-3"
      data-testid="section-time-to-nudge"
    >
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
            Time to nudge
          </div>
          <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
            {state.items.length} lead{state.items.length === 1 ? "" : "s"} you touched but haven&rsquo;t nudged
          </h2>
          <p className="text-[13px] text-[var(--bh-ink-mute)] mt-0.5 max-w-2xl leading-relaxed">
            The most valuable follow-up: owners buy from whoever is still
            present. One tap opens the same draft on your phone.
          </p>
        </div>
        {state.items.length > 3 && (
          <button
            onClick={() => setCollapsed((c) => !c)}
            data-testid="nudge-toggle"
            className="text-[12px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
          >
            {collapsed ? `Show all ${state.items.length}` : "Show fewer"}
            <ChevronRight size={13} strokeWidth={1.75} />
          </button>
        )}
      </div>

      <div className="space-y-2">
        {shown.map((item) => (
          <NudgeRow key={item.opportunity_id} item={item} />
        ))}
        {hiddenCount > 0 && collapsed && (
          <div className="text-[11px] text-[var(--bh-ink-mute)] text-center pt-1">
            +{hiddenCount} more waiting for a nudge
          </div>
        )}
      </div>
    </section>
  );
};

export default TimeToNudge;
