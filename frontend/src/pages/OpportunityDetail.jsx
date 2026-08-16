import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import TopHeader from "@/components/TopHeader";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import StatusBadge from "@/components/StatusBadge";
import MissionBadge from "@/components/MissionBadge";
import EditableDecisionPanel from "@/components/EditableDecisionPanel";
import DraftNoteDrawer from "@/components/DraftNoteDrawer";
import OpenInMessages from "@/components/OpenInMessages";
import ContactResults from "@/components/ContactResults";
import { api } from "@/lib/api";
import { fmtMoney, fmtMoneyFull, fmtDate, fmtDateTime, moneyDisplay, sourceLabel } from "@/lib/formatters";
import { needsConfirmation } from "@/lib/priority";
import { queueBucket, outreachAllowed } from "@/lib/queue";
import {
  ArrowLeft,
  MapPin,
  Phone,
  Mail,
  FileText,
  ShieldAlert,
  Info,
  Sparkles,
  Search,
  Clock3,
  CheckCircle2,
  Send,
  Trophy,
  XCircle,
  Gauge,
  Target,
} from "lucide-react";

const ACTION_BUTTONS = [
  { label: "Get more info first", status: "Needs research", icon: Search, tone: "ghost" },
  { label: "Won", status: "Won", icon: Trophy, tone: "success" },
  { label: "Lost", status: "Lost", icon: XCircle, tone: "danger" },
];

// Governed queue chip colors — Ready is brass, Contacted is olive/warm,
// All Projects is a muted neutral so it never visually outranks the two
// active queues.
const QUEUE_CHIP_STYLES = {
  "Ready to Contact": { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" },
  Contacted: { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)" },
  "All Projects": { fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" },
};

const GovernedChip = ({ label, value, tone = "neutral", testId }) => {
  if (value === null || value === undefined || value === "") return null;
  const styles =
    tone === "queue"
      ? QUEUE_CHIP_STYLES[value] || QUEUE_CHIP_STYLES["All Projects"]
      : tone === "warn"
        ? { fg: "var(--bh-brass-2)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" }
        : { fg: "var(--bh-ink-2)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" };
  return (
    <span
      data-testid={testId}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-tight"
      style={{ color: styles.fg, background: styles.bg, borderColor: styles.border }}
    >
      <span className="mono text-[9px] uppercase tracking-widest opacity-75">{label}</span>
      <span>{value}</span>
    </span>
  );
};

const GovernedSignal = ({ label, value, testId }) => (
  <div data-testid={testId}>
    <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
      {label}
    </div>
    <div className="mt-0.5 text-[13px] text-[var(--bh-ink)] font-medium">
      {value ?? <span className="text-[var(--bh-ink-3)] italic">—</span>}
    </div>
  </div>
);

const activityIcon = (t) => {
  const map = {
    discovered: Sparkles,
    analysis: Gauge,
    status_change: CheckCircle2,
    mission_change: Target,
    call: Phone,
    text: Send,
    email: Mail,
    research: Search,
    estimate: FileText,
    outcome: Trophy,
  };
  return map[t] || Info;
};

const SectionHeading = ({ title, hint }) => (
  <div className="flex items-baseline justify-between mb-3">
    <h3 className="font-display text-lg font-bold text-[var(--bh-ink)]">{title}</h3>
    {hint ? (
      <div className="bh-eyebrow">
        {hint}
      </div>
    ) : null}
  </div>
);

const KV = ({ label, value, mono, testId }) => (
  <div className="py-2 border-b bh-hairline last:border-b-0" data-testid={testId}>
    <div className="bh-eyebrow">
      {label}
    </div>
    <div className={"mt-1 text-sm text-[var(--bh-ink)] " + (mono ? "mono" : "")}>
      {value ?? <span className="text-neutral-600 italic">Not available yet</span>}
    </div>
  </div>
);

const Meter = ({ label, level }) => {
  const map = { High: 3, Hot: 3, Direct: 3, Medium: 2, Warm: 2, "Warm intro": 2, Low: 1, Cold: 1, Indirect: 1, Unknown: 0, "Not confirmed": 0 };
  let val = 0;
  let display = level ?? "—";
  if (typeof level === "number") {
    // Numeric score — normalise: 0–3 direct, 0–10 tenths, 0–100 percent.
    const n = level;
    if (n <= 3) val = n;
    else if (n <= 10) val = n >= 7 ? 3 : n >= 4 ? 2 : n >= 1 ? 1 : 0;
    else val = n >= 70 ? 3 : n >= 40 ? 2 : n >= 1 ? 1 : 0;
    display = n;
  } else if (typeof level === "string") {
    val = map[level] ?? 0;
  }
  const color =
    val === 3 ? "bg-emerald-500" : val === 2 ? "bg-amber-500" : val === 1 ? "bg-red-500/70" : "bg-neutral-700";
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="bh-eyebrow">{label}</span>
        <span className="text-xs text-[var(--bh-ink-2)]">{display}</span>
      </div>
      <div className="mt-1.5 flex gap-1">
        {[1, 2, 3].map((i) => (
          <div
            key={`bar-${i}`}
            className={"h-1 flex-1 rounded " + (i <= val ? color : "bg-white/[0.06]")}
          />
        ))}
      </div>
    </div>
  );
};

const OpportunityDetail = () => {
  const { id } = useParams();
  const [opp, setOpp] = useState(null);
  const [busy, setBusy] = useState(null);
  const [draftOpen, setDraftOpen] = useState(false);

  useEffect(() => {
    api.getOpportunity(id).then(setOpp).catch(() => setOpp(null));
  }, [id]);

  const handleStatus = async (status) => {
    setBusy(status);
    try {
      const updated = await api.updateStatus(id, status);
      setOpp(updated);
      toast.success(`Status → ${status}`);
    } catch (e) {
      toast.error("Could not update status");
    } finally {
      setBusy(null);
    }
  };

  if (!opp) {
    return (
      <>
        <TopHeader pageTitle="Opportunity" subtitle="Loading…" />
        <div className="px-4 lg:px-8 py-10 text-[var(--bh-ink-mute)]">Loading…</div>
      </>
    );
  }

  return (
    <>
      <TopHeader
        pageTitle={opp.name}
        subtitle={`Found on ${sourceLabel(opp.source)}`}
      />

      <div className="px-4 lg:px-8 py-6 space-y-6">
        <Link
          to="/opportunities"
          className="inline-flex items-center gap-1.5 text-xs text-[var(--bh-ink-mute)] hover:text-amber-400"
          data-testid="back-to-opps"
        >
          <ArrowLeft size={13} /> Back to Project List
        </Link>

        {needsConfirmation(opp) && (
          <div
            data-testid="needs-confirmation-banner"
            className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100"
          >
            <div className="font-medium text-amber-200">Needs confirmation</div>
            <p className="mt-1 text-[13px] leading-relaxed text-amber-100/80">
              Outreach history says something was sent, but no result has been
              confirmed yet. Tap one of the result buttons below (They replied,
              No reply yet, Not interested, etc.) to keep the tracker honest.
            </p>
          </div>
        )}

        {/* Hero */}
        <section
          data-testid="opp-hero"
          className="bh-surface rounded-md p-5 lg:p-6 border-t border-t-amber-500/60"
        >
          <div className="grid lg:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
            <div className="min-w-0">
              {/* Primary governed badges — Current Queue is the single source
                  of truth for placement and every action gate. Contact
                  Readiness supplies the not-ready reason; Contact State
                  supplies follow-up context. */}
              <div
                className="flex items-center gap-2 flex-wrap"
                data-testid="governed-badges"
              >
                <GovernedChip
                  label="Queue"
                  value={opp.current_queue || "Not classified"}
                  tone="queue"
                  testId="governed-current-queue"
                />
                {opp.contact_readiness && (
                  <GovernedChip
                    label="Readiness"
                    value={opp.contact_readiness}
                    tone="warn"
                    testId="governed-contact-readiness"
                  />
                )}
                {opp.contact_state && queueBucket(opp) !== "all" && (
                  <GovernedChip
                    label="State"
                    value={opp.contact_state}
                    testId="governed-contact-state"
                  />
                )}
              </div>
              <h1 className="mt-2 font-display text-3xl lg:text-4xl font-bold text-[var(--bh-ink)] tracking-tight">
                {opp.name}
              </h1>
              <div className="mt-2 flex items-center gap-2 text-sm text-[var(--bh-ink-mute)]">
                <MapPin size={14} className="text-[var(--bh-ink-mute)]" />
                {opp.project_address}
              </div>
              <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4 min-w-0">
                <div data-testid="governed-priority-score">
                  <div className="bh-eyebrow">Governed priority score</div>
                  <div className="font-display text-2xl lg:text-3xl font-bold text-[var(--bh-ink)] tabular-nums mt-1">
                    {typeof opp.governed_priority_score === "number"
                      ? opp.governed_priority_score
                      : <span className="text-[var(--bh-ink-mute)] italic text-[16px]">Not scored</span>}
                  </div>
                </div>
                <GovernedSignal label="Money signal" value={opp.money_signal} testId="governed-money-signal" />
                <GovernedSignal label="Premium fit" value={opp.premium_fit} testId="governed-premium-fit" />
                <GovernedSignal label="Evidence" value={opp.evidence_status} testId="governed-evidence-status" />
                <GovernedSignal label="Freshness" value={opp.freshness} testId="governed-freshness" />
                <GovernedSignal
                  label="Possible work value"
                  value={moneyDisplay(opp)}
                  testId="governed-work-value"
                />
                <GovernedSignal label="Found on" value={sourceLabel(opp.source)} />
                <GovernedSignal label="Project type" value={opp.project_type} />
              </div>
              {(opp.priority_explanation || opp.current_recommendation || opp.project_fit_reason) && (
                <div className="mt-5 border-t bh-hairline pt-4 space-y-3">
                  {opp.priority_explanation && (
                    <div data-testid="governed-why-this-matters">
                      <div className="bh-eyebrow">Why this matters</div>
                      <p className="mt-1 text-sm text-[var(--bh-ink-2)] leading-relaxed">
                        {opp.priority_explanation}
                      </p>
                    </div>
                  )}
                  {opp.current_recommendation && (
                    <div data-testid="governed-what-to-do-next">
                      <div className="bh-eyebrow">What to do next</div>
                      <p className="mt-1 text-sm text-amber-200/90 leading-relaxed">
                        {opp.current_recommendation}
                      </p>
                    </div>
                  )}
                  {opp.project_fit_reason && (
                    <div data-testid="governed-project-fit-reason">
                      <div className="bh-eyebrow">Project fit reason</div>
                      <p className="mt-1 text-[13px] text-[var(--bh-ink-3)] leading-relaxed">
                        {opp.project_fit_reason}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Primary action panel */}
            <div className="bh-surface-2 rounded p-4 min-w-0">
              <div className="bh-eyebrow">Actions</div>
              <div className="mt-3 border-t bh-hairline pt-3 space-y-2">
                {(() => {
                  const bucket = queueBucket(opp);
                  if (bucket === "all") {
                    return (
                      <div
                        data-testid="no-outreach-notice"
                        className="rounded-md border p-3 text-[12.5px] text-[var(--bh-ink-3)]"
                        style={{ borderColor: "var(--bh-hair)" }}
                      >
                        This record is in All Projects — the classifier hasn&apos;t
                        approved outreach yet. Add the missing evidence in
                        Airtable to promote it to Ready to Contact.
                      </div>
                    );
                  }
                  return (
                    <>
                      <OpenInMessages opportunity={opp} variant="panel" />
                      <ContactResults opportunity={opp} onSaved={setOpp} />
                    </>
                  );
                })()}
                <div className="space-y-1.5 pt-1">
                {ACTION_BUTTONS.map((a) => {
                  return (
                    <React.Fragment key={a.status}>
                      <button
                        data-testid={`action-${a.status}`}
                        disabled={busy === a.status || opp.status === a.status}
                        onClick={() => handleStatus(a.status)}
                        className={
                          "w-full flex items-center gap-2 px-3 h-9 rounded text-sm transition-colors duration-150 " +
                          (a.tone === "primary"
                            ? "bg-amber-500 text-neutral-950 hover:bg-amber-400 font-medium"
                            : a.tone === "success"
                              ? "border bh-hairline text-emerald-300 hover:bg-emerald-500/10"
                              : a.tone === "danger"
                                ? "border bh-hairline text-red-300 hover:bg-red-500/10"
                                : "border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)]") +
                          (opp.status === a.status ? " opacity-40" : "") +
                          " disabled:cursor-not-allowed"
                        }
                      >
                        <a.icon size={14} />
                        {a.label}
                      </button>
                    </React.Fragment>
                  );
                })}
                {/* Draft a Note is retired. The single Email Now / Follow
                    Up Email button in OpenInMessages is the ONLY outreach
                    entry point on Ready and Contacted records. */}
                </div>
              </div>
            </div>
          </div>
        </section>

        {opp.lane === "partner" && (
          <DraftNoteDrawer
            open={draftOpen}
            onOpenChange={setDraftOpen}
            opportunity={opp}
          />
        )}

        <div className="grid lg:grid-cols-3 gap-6">
          {/* Left col: Intelligence + Contact + Property */}
          <div className="lg:col-span-2 space-y-6">
            {/* Intelligence */}
            <section className="bh-surface rounded-md p-5">
              <SectionHeading
                title="Why this project matters"
              />
              <div className="grid md:grid-cols-2 gap-5">
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] mb-1">
                    Why this recommendation
                  </div>
                  <p className="text-sm text-[var(--bh-ink-2)] leading-relaxed">
                    {opp.recommendation_reason || "—"}
                  </p>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] mb-1">
                    Evidence summary
                  </div>
                  <p className="text-sm text-[var(--bh-ink-2)] leading-relaxed">
                    {opp.evidence_summary || "—"}
                  </p>
                </div>
              </div>

              <div className="mt-5 grid sm:grid-cols-2 gap-5">
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] mb-1.5 inline-flex items-center gap-1.5">
                    <Info size={11} /> Missing information
                  </div>
                  {opp.missing_information?.length ? (
                    <ul className="space-y-1">
                      {opp.missing_information.map((m, i) => (
                        <li
                          key={`missing-${m}-${i}`}
                          className="text-sm text-amber-200/90 flex items-start gap-2"
                        >
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-400" />
                          {m}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-sm text-[var(--bh-ink-mute)]">
                      Nothing critical missing.
                    </div>
                  )}
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] mb-1.5 inline-flex items-center gap-1.5">
                    <ShieldAlert size={11} /> Risk flags
                  </div>
                  {opp.risk_flags?.length ? (
                    <ul className="space-y-1">
                      {opp.risk_flags.map((m, i) => (
                        <li
                          key={`risk-${m}-${i}`}
                          className="text-sm text-red-300 flex items-start gap-2"
                        >
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-red-400" />
                          {m}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-sm text-[var(--bh-ink-mute)]">
                      No risk flags detected.
                    </div>
                  )}
                </div>
              </div>

            <div className="mt-5 grid grid-cols-2 sm:grid-cols-5 gap-4 opacity-70">
              <div className="col-span-full mb-1 mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
                More details · legacy signals (Airtable + Make own the governed layer above)
              </div>
              <Meter label="Opportunity Fit" level={opp.opportunity_fit} />
              <Meter label="Momentum" level={opp.momentum} />
              <Meter label="Reachability" level={opp.reachability} />
              <Meter label="Can I reach them?" level={opp.contact_confidence} />
              <Meter label="How solid is the info" level={opp.evidence_confidence} />
            </div>
            </section>

            {/* Contact */}
            <section className="bh-surface rounded-md p-5">
              <SectionHeading title="Who to talk to" />
              <div className="grid sm:grid-cols-2 gap-x-6">
                <KV label="Decision maker" value={opp.decision_maker} testId="kv-decision-maker" />
                <KV label="Phone" value={opp.phone} mono testId="kv-phone" />
                <KV label="Email" value={opp.email} testId="kv-email" />
                <KV label="Company" value={opp.company} testId="kv-company" />
                <KV label="Applicant" value={opp.applicant} />
                <KV label="Contractor on record" value={opp.contractor} />
                <KV label="Owner" value={opp.owner} />
              </div>
            </section>

            {/* Property / Project */}
            <section className="bh-surface rounded-md p-5">
              <SectionHeading title="The project" />
              <div className="grid sm:grid-cols-2 gap-x-6">
                <KV label="Project address" value={opp.project_address} />
                <KV label="Project type" value={opp.project_type} />
                <KV label="Permit number" value={opp.permit_number} mono />
                <KV label="Permit source" value={opp.permit_source} />
                <KV label="Filing date" value={fmtDate(opp.permit_filing_date)} mono />
                <KV
                  label="Construction value"
                  value={opp.construction_value ? fmtMoneyFull(opp.construction_value) : null}
                  mono
                />
                <KV
                  label="Permit description"
                  value={opp.permit_description}
                />
              </div>
            </section>

            <EditableDecisionPanel opp={opp} onUpdated={setOpp} />
          </div>

          {/* Right col: Activity */}
          <div className="space-y-6">
            <section className="bh-surface rounded-md p-5">
              <SectionHeading title="Recent activity" />
              <ol className="relative border-l bh-hairline pl-5 space-y-4">
                {(opp.activity_timeline || []).map((a, i) => {
                  const Icon = activityIcon(a.type);
                  return (
                    <li key={a.timestamp ? `${a.type}-${a.timestamp}` : `activity-${i}`} className="relative">
                      <span className="absolute -left-[27px] top-0.5 w-4 h-4 rounded-full bg-[color:var(--bh-surface)] border bh-hairline-strong flex items-center justify-center">
                        <Icon size={9} className="text-amber-400" />
                      </span>
                      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] flex items-center gap-2">
                        <Clock3 size={10} />
                        {fmtDateTime(a.timestamp)}
                      </div>
                      <div className="text-sm text-[var(--bh-ink-2)] mt-0.5">
                        {a.note}
                      </div>
                    </li>
                  );
                })}
                {(!opp.activity_timeline || opp.activity_timeline.length === 0) && (
                  <li className="text-sm text-[var(--bh-ink-mute)]">No activity yet.</li>
                )}
              </ol>
            </section>
          </div>
        </div>
      </div>
    </>
  );
};

export default OpportunityDetail;
