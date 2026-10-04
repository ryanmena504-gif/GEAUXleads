import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ExternalLink, Loader2, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { fmtMoney } from "@/lib/formatters";
import PassSheet from "@/components/PassSheet";

/**
 * Two Home sections that pull leads out of the places the pipeline left them.
 *
 * WaitingOnYou — permits the AI decision engine approved
 * (ready_for_campaign_review) that the Make promotion step never moved into
 * Leads. "Add to my list" promotes one; "Pass" records why not.
 *
 * OnePhoneAway — strong leads whose only blocker is a missing public contact.
 * "Find contact" runs the Contact Finder agent, which fills the phone/email
 * back on the lead; nothing is sent to anyone.
 */

const pretty = (s) => (typeof s === "string" ? s.replace(/_/g, " ") : s);

const Chapter = ({ title, aside, children, testId }) => (
  <section data-testid={testId} className="space-y-3">
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b bh-hairline pb-2">
      <h2 className="font-display text-[21px] tracking-tight text-[var(--bh-ink)] whitespace-nowrap">{title}</h2>
      {aside && <span className="text-[12px] text-[var(--bh-ink-mute)]">{aside}</span>}
    </div>
    {children}
  </section>
);

const SignalCard = ({ s, busy, onAdd, onPass }) => {
  const value = s.ai_value || s.permit_value;
  return (
    <article data-testid={`waiting-signal-${s.id}`} className="bh-ticket p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[15px] font-semibold text-[var(--bh-ink)] truncate">{s.address || "Address not listed"}</div>
          <div className="mt-0.5 text-[12.5px] text-[var(--bh-ink-3)] capitalize">
            {pretty(s.project_type) || s.work_class || "Permit"}
          </div>
        </div>
        <div className="text-right shrink-0">
          {value ? (
            <div className="font-display text-[17px] tabular-nums text-[var(--bh-ink)]">{fmtMoney(value)}</div>
          ) : null}
          {typeof s.ai_confidence === "number" && (
            <div className="text-[11px] text-[var(--bh-ink-mute)]">
              {s.ai_confidence}% sure{s.service_fit ? ` · ${s.service_fit} fit` : ""}
            </div>
          )}
        </div>
      </div>
      {s.why && <p className="mt-2 text-[13px] leading-relaxed text-[var(--bh-ink-2)] line-clamp-3">{s.why}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onAdd(s)}
          data-testid={`promote-${s.id}`}
          className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-md text-[13px] font-semibold disabled:opacity-60"
          style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add to my list
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onPass(s)}
          data-testid={`pass-signal-${s.id}`}
          className="inline-flex items-center h-9 px-3 rounded-md text-[12px] font-medium text-[var(--bh-ink-3)] hover:text-[var(--bh-clay)] hover:bg-[var(--bh-clay-mute)]"
        >
          Pass
        </button>
        {s.source_url && (
          <a
            href={s.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
          >
            <ExternalLink size={12} /> Permit {s.permit_number || ""}
          </a>
        )}
      </div>
    </article>
  );
};

export const WaitingOnYou = ({ onChanged }) => {
  const [data, setData] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [passTarget, setPassTarget] = useState(null);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(() => {
    api
      .pipelineWaiting()
      .then(setData)
      .catch(() => setData({ available: false, items: [] }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const drop = (id) => setData((d) => (d ? { ...d, items: d.items.filter((x) => x.id !== id) } : d));

  const add = async (s) => {
    setBusyId(s.id);
    try {
      await api.promoteSignal(s.id);
      drop(s.id);
      toast.success(`${s.address || "Lead"} is on your list. The classifier will pick it up on its next run.`);
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't add it");
      if (e?.response?.status === 409) drop(s.id);
    } finally {
      setBusyId(null);
    }
  };

  if (!data || !data.available || data.items.length === 0) return null;
  const items = showAll ? data.items : data.items.slice(0, 5);

  return (
    <Chapter
      testId="section-waiting-on-you"
      title="Waiting on you"
      aside={`${data.items.length} your AI approved that never reached your list`}
    >
      <div className="space-y-2">
        {items.map((s) => (
          <SignalCard key={s.id} s={s} busy={busyId === s.id} onAdd={add} onPass={setPassTarget} />
        ))}
      </div>
      {data.items.length > 5 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="text-[12.5px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
        >
          {showAll ? "Show fewer" : `Show all ${data.items.length}`}
        </button>
      )}
      <PassSheet
        opp={passTarget ? { id: passTarget.id, name: passTarget.address } : null}
        open={Boolean(passTarget)}
        onOpenChange={(v) => !v && setPassTarget(null)}
        submit={async (reason, note) => {
          await api.passSignal(passTarget.id, reason.key, note || undefined);
          drop(passTarget.id);
        }}
      />
    </Chapter>
  );
};

const CLOSED = new Set(["Won", "Lost", "Disqualified"]);

export const OnePhoneAway = ({ items }) => {
  const [busyId, setBusyId] = useState(null);
  const [started, setStarted] = useState(() => new Set());

  const leads = useMemo(
    () =>
      (items || [])
        .filter(
          (o) =>
            o.contact_readiness === "Needs Public Contact" &&
            !CLOSED.has(o.status) &&
            // Already in Ready / Contacted → it's in the action lists above.
            !["Ready to Contact", "Contacted"].includes(o.current_queue) &&
            typeof o.governed_priority_score === "number" &&
            o.governed_priority_score >= 70,
        )
        .sort((a, b) => b.governed_priority_score - a.governed_priority_score)
        .slice(0, 10),
    [items],
  );

  const find = async (o) => {
    setBusyId(o.id);
    try {
      await api.findContact(o.id);
      setStarted((s) => new Set(s).add(o.id));
      toast.success("Contact finder is searching — results land on the lead in about a minute.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't start the contact finder");
    } finally {
      setBusyId(null);
    }
  };

  if (leads.length === 0) return null;
  return (
    <Chapter
      testId="section-one-phone-away"
      title="One phone number away"
      aside="Strong fits with no public contact yet"
    >
      <div className="space-y-1.5">
        {leads.map((o) => (
          <div key={o.id} data-testid={`phone-away-${o.id}`} className="bh-surface rounded-md p-3 flex items-center gap-3">
            <span
              className="w-10 shrink-0 text-center font-display text-[18px] tabular-nums text-[var(--bh-brass)]"
              title="Governed priority score"
            >
              {o.governed_priority_score}
            </span>
            <Link to={`/opportunities/${o.id}`} className="flex-1 min-w-0 group">
              <div className="text-[14px] font-semibold text-[var(--bh-ink)] truncate group-hover:underline">{o.name}</div>
              <div className="text-[12px] text-[var(--bh-ink-mute)] truncate">
                {[o.project_type, o.company].filter(Boolean).join(" · ") || o.project_address}
              </div>
            </Link>
            <button
              type="button"
              disabled={busyId === o.id || started.has(o.id)}
              onClick={() => find(o)}
              data-testid={`find-contact-${o.id}`}
              className="shrink-0 inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-[12px] font-semibold border bh-hairline text-[var(--bh-ink)] hover:bg-[var(--bh-surface-2)] disabled:opacity-60"
            >
              {busyId === o.id ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
              {started.has(o.id) ? "Searching…" : "Find contact"}
            </button>
          </div>
        ))}
      </div>
    </Chapter>
  );
};
