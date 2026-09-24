import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Phone, ChevronRight, ArrowLeft, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { moneyDisplay } from "@/lib/formatters";
import { queueBucket } from "@/lib/queue";
import OpenInMessages from "@/components/OpenInMessages";

/**
 * Lookup — reverse-lookup card. Ryan's iOS Shortcut opens
 * `/lookup?phone=+15045550142` when an inbound call/text lands from an
 * unknown number. The page fetches `/api/opportunities/by-phone/:number`
 * and shows the compact governed card with a one-tap Email Now / Follow
 * Up Email button (when eligible).
 *
 * Zero writes on view. The lookup endpoint is read-only.
 */

const QUEUE_STYLES = {
  "Ready to Contact": { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" },
  Contacted: { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)" },
  "All Projects": { fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" },
};

const QueueBadge = ({ value }) => {
  const s = QUEUE_STYLES[value] || QUEUE_STYLES["All Projects"];
  return (
    <span
      data-testid="lookup-current-queue"
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-semibold"
      style={{ color: s.fg, background: s.bg, borderColor: s.border }}
    >
      <span className="mono text-[9.5px] uppercase tracking-widest opacity-75">Queue</span>
      {value || "Not classified"}
    </span>
  );
};

const Row = ({ label, value, testid }) => {
  if (!value) return null;
  return (
    <div className="pt-3 border-t bh-hairline first:border-t-0 first:pt-0" data-testid={testid}>
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
        {label}
      </div>
      <div className="mt-1 text-[13.5px] text-[var(--bh-ink-2)] leading-relaxed">
        {value}
      </div>
    </div>
  );
};

const Lookup = () => {
  const [params] = useSearchParams();
  const phone = params.get("phone") || "";
  const [state, setState] = useState({ loading: true, error: null, opp: null });

  useEffect(() => {
    if (!phone.trim()) {
      setState({ loading: false, error: "No phone number provided", opp: null });
      return;
    }
    let mounted = true;
    api.lookupByPhone(phone)
      .then((opp) => mounted && setState({ loading: false, error: null, opp }))
      .catch((err) => {
        const detail = err?.response?.data?.detail || err?.message || "Lookup failed";
        mounted && setState({ loading: false, error: detail, opp: null });
      });
    return () => { mounted = false; };
  }, [phone]);

  return (
    <div className="px-4 lg:px-8 py-6 max-w-3xl">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] mb-4"
      >
        <ArrowLeft size={13} /> Home
      </Link>

      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-brass)]">
        <Phone size={11} className="inline-block -mt-0.5 mr-1.5" strokeWidth={1.75} />
        Reverse lookup
      </div>
      <h1
        className="mt-1 font-display text-[26px] font-bold text-[var(--bh-ink)] tracking-tight"
        data-testid="lookup-headline"
      >
        Who is {phone || "—"}?
      </h1>

      {state.loading && (
        <div data-testid="lookup-loading" className="mt-6 rounded-md border bh-hairline p-4 text-[13px] text-[var(--bh-ink-3)]">
          Looking up {phone}…
        </div>
      )}

      {state.error && !state.loading && (
        <div
          data-testid="lookup-not-found"
          className="mt-6 rounded-md border p-5 space-y-2"
          style={{ background: "var(--bh-surface-2)", borderColor: "var(--bh-hair)" }}
        >
          <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
            No match on file
          </div>
          <div className="text-[15px] font-semibold text-[var(--bh-ink)]">
            {phone} isn&apos;t in Bloodhound.
          </div>
          <div className="text-[12.5px] text-[var(--bh-ink-3)]">
            {state.error}. If this is a lead, add them in Airtable and the
            classifier will pick them up on the next sync.
          </div>
        </div>
      )}

      {state.opp && !state.loading && (
        <div
          data-testid="lookup-card"
          className="mt-6 rounded-md border p-5 lg:p-6 space-y-4"
          style={{ background: "var(--bh-surface)", borderColor: "var(--bh-hair-warm)" }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <QueueBadge value={state.opp.current_queue} />
              <h2
                className="mt-2 font-display text-[22px] font-bold text-[var(--bh-ink)] leading-tight"
                data-testid="lookup-name"
              >
                {state.opp.name}
              </h2>
              {state.opp.project_type && (
                <div className="mt-1 text-[12.5px] text-[var(--bh-ink-mute)]">
                  {state.opp.project_type}
                  {state.opp.project_address ? ` · ${state.opp.project_address}` : ""}
                </div>
              )}
            </div>
            {typeof state.opp.governed_priority_score === "number" && (
              <div className="text-right shrink-0">
                <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
                  Score
                </div>
                <div
                  className="font-display text-[28px] font-bold text-[var(--bh-ink)] tabular-nums"
                  data-testid="lookup-score"
                >
                  {state.opp.governed_priority_score}
                </div>
              </div>
            )}
          </div>

          <div>
            <OpenInMessages opportunity={state.opp} variant="pill" />
          </div>

          <div className="space-y-3">
            <Row label="Why this matters" value={state.opp.priority_explanation} testid="lookup-why" />
            <Row label="What to do next" value={state.opp.current_recommendation} testid="lookup-what-next" />
            <Row label="Readiness" value={state.opp.contact_readiness} />
            <Row label="Contact state" value={state.opp.contact_state} />
            <Row label="Possible work value" value={moneyDisplay(state.opp)} />
          </div>

          <div className="pt-3 border-t bh-hairline flex items-center justify-between">
            <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
              <ShieldCheck size={11} style={{ color: "var(--bh-olive)" }} />
              Read-only lookup — no state changed.
            </div>
            <Link
              to={`/opportunities/${state.opp.id}`}
              data-testid="lookup-open-detail"
              className="inline-flex items-center gap-1 text-[12.5px] font-medium text-[var(--bh-brass)] hover:text-white"
            >
              Open full record <ChevronRight size={12} />
            </Link>
          </div>

          {queueBucket(state.opp) === "all" && (
            <div className="text-[11.5px] text-[var(--bh-ink-3)]">
              This record is in All Projects — the classifier hasn&apos;t approved
              outreach yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Lookup;
