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
import LandlordPortfolio from "@/components/LandlordPortfolio";
import ResearchPanel from "@/components/ResearchPanel";
import ScoreExplanationCard from "@/components/ScoreExplanationCard";
import ContactStatusChip from "@/components/ContactStatusChip";
import CompletedProjectProofCard from "@/components/CompletedProjectProofCard";
import CheckPortfolioButton from "@/components/CheckPortfolioButton";
import PreviewNotice from "@/components/PreviewNotice";
import WriteOutreachDraftButton, { OutreachDraftCard } from "@/components/WriteOutreachDraftButton";
import useAirtableRecordUrl from "@/hooks/useAirtableRecordUrl";
import { api } from "@/lib/api";
import { fmtMoney, fmtMoneyFull, fmtDate, fmtDateTime, fmtMoneyOrStatus, moneyDisplay, sourceLabel } from "@/lib/formatters";
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
  User,
  Network,
  Building2,
  Signal,
  Hammer,
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
  const [releasing, setReleasing] = useState(false);
  const airtableUrlFor = useAirtableRecordUrl();

  useEffect(() => {
    api.getOpportunity(id).then(setOpp).catch(() => setOpp(null));
  }, [id]);

  const releaseHold = async () => {
    setReleasing(true);
    try {
      const r = await api.leadsAction(id, { action: "release_hold" });
      if (!r?.persisted) throw new Error("Airtable write failed");
      toast.success("Hold released — Hunt status → Investigating. The classifier will re-evaluate on its next run.");
      setOpp(await api.getOpportunity(id));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not release hold");
    } finally {
      setReleasing(false);
    }
  };

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
              <div className="mt-4 grid grid-cols-2 sm:grid-cols-5 gap-4">
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Priority
                  </div>
                  <div className="mt-1">
                    <PriorityScore
                      score={opp.priority_score}
                      band={opp.priority_band}
                      size="lg"
                    />
                  </div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Official project value
                  </div>
                  <div className="font-display text-2xl lg:text-3xl font-bold text-neutral-100 tabular-nums mt-1">
                    {fmtMoneyOrStatus(opp.construction_value, "Not public")}
                  </div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Possible work for us
                  </div>
                  <div className="font-display text-2xl lg:text-3xl font-bold text-neutral-100 tabular-nums mt-1">
                    {fmtMoneyOrStatus(opp.estimated_value, "Not estimated yet")}
                  </div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Source
                  </div>
                  <div className="mt-1 text-neutral-100 font-medium">
                    {sourceLabel(opp.source)}
                  </div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    Project type
                  </div>
                  <div className="mt-1 text-neutral-100 font-medium">
                    {opp.project_type}
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
                    const atUrl = airtableUrlFor(opp?.id);
                    return (
                      <div
                        data-testid="no-outreach-notice"
                        className="rounded-md border p-3 text-[12.5px] text-[var(--bh-ink-3)] space-y-2"
                        style={{ borderColor: "var(--bh-hair)" }}
                      >
                        <div>
                          This record is in All Projects — the classifier hasn&apos;t
                          approved outreach yet. Add the missing evidence in
                          Airtable to promote it to Ready to Contact.
                        </div>
                        {opp?.hunt_status === "Paused" && (
                          <div
                            data-testid="hold-notice"
                            className="rounded border p-2.5 space-y-2"
                            style={{ borderColor: "var(--bh-hair-warm)", background: "var(--bh-brass-mute)" }}
                          >
                            <div className="text-[var(--bh-ink-2)]">
                              <span className="font-semibold">On hold.</span> Hunt status is
                              &ldquo;Paused&rdquo; — set when you tapped Save for later. The
                              classifier skips paused records, so this gate won&apos;t re-open
                              until the hold is released.
                            </div>
                            <button
                              type="button"
                              data-testid="release-hold-btn"
                              disabled={releasing}
                              onClick={releaseHold}
                              className="h-9 px-3 rounded text-[12.5px] font-medium text-white disabled:opacity-60 transition-colors duration-150"
                              style={{ background: "var(--bh-brass)" }}
                            >
                              {releasing ? "Releasing…" : "Release hold → Investigating"}
                            </button>
                          </div>
                        )}
                        {atUrl && (
                          <a
                            href={atUrl}
                            target="_blank"
                            rel="noreferrer noopener"
                            data-testid="open-in-airtable-link"
                            className="inline-flex items-center gap-1.5 text-[12px] font-medium"
                            style={{ color: "var(--bh-brass)" }}
                          >
                            Open in Airtable →
                          </a>
                        )}
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
            {opp.lane === "landlord" && (
              <LandlordPortfolio opportunityId={opp.id} />
            )}
            {/* Completed Project Proof — read-only card populated by
                Claude/Make's Portfolio Check webhook. Card auto-hides
                when no Portfolio_* field is set. Button renders always
                so the operator can trigger a check on any lead. */}
            <section className="flex items-center justify-between gap-3 flex-wrap"
                     data-testid="portfolio-check-toolbar">
              <div className="text-[12.5px] text-[var(--bh-ink-3)] leading-snug max-w-[560px]">
                Find genuine public evidence of this business&rsquo;s
                completed work before you write to them. Real web search
                — one-off, per-record. Nothing sends automatically.
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <CheckPortfolioButton opportunity={opp} onOpportunityUpdated={setOpp} />
                {/* Draft control → same global gate as every other outreach control. */}
                {outreachAllowed(opp) !== "none" && (
                  <WriteOutreachDraftButton opportunity={opp} onOpportunityUpdated={setOpp} />
                )}
              </div>
            </section>
            <CompletedProjectProofCard opportunity={opp} />
            {outreachAllowed(opp) !== "none" && <OutreachDraftCard opportunity={opp} />}
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

            {/* Governed score / priority — read-only, provenance-labeled */}
            <ScoreExplanationCard opp={opp} testId={`score-card-${opp.id}`} />

            {/* Contact */}
            <section className="bh-surface rounded-md p-5">
              <SectionHeading title="Who to talk to" />
              <div className="mb-3">
                <ContactStatusChip record={opp} testId={`opp-contact-status-${opp.id}`} />
              </div>
              <div className="grid sm:grid-cols-2 gap-x-6">
                <KV label="Decision maker" value={opp.decision_maker} testId="kv-decision-maker" />
                <KV label="Phone" value={opp.phone} mono testId="kv-phone" />
                <KV label="Email" value={opp.email} testId="kv-email" />
                <KV label="Company" value={opp.company} testId="kv-company" />
                <KV label="Applicant" value={opp.applicant} />
                <KV label="Contractor on record" value={opp.contractor} />
                <KV label="Owner" value={opp.owner} />
              </div>
              <div className="mt-4">
                <ResearchPanel
                  researchType="decision_maker"
                  recordId={opp.id}
                  query={`Who runs the business or owns the property at ${opp.project_address || opp.name}? Business/lead name: ${opp.name}. Company field: ${opp.company || "(none)"}. Any decision maker on file: ${opp.decision_maker || "(none)"}. Give verified name, role, and one-line context with citations.`}
                  label={opp.decision_maker ? "Verify this decision maker" : "Who runs this?"}
                  hint="Grounded web lookup with citations. Read-only — nothing writes back to Airtable."
                  testId={`research-dm-${opp.id}`}
                />
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
                  label="Official project value"
                  value={fmtMoneyOrStatus(opp.construction_value, "Not public")}
                  mono
                />
                <KV
                  label="Possible work for us"
                  value={fmtMoneyOrStatus(opp.estimated_value, "Not estimated yet")}
                  mono
                />
                <KV
                  label="Permit description"
                  value={opp.permit_description}
                />
              </div>
              {(opp.permit_description || opp.permit_number) && (
                <div className="mt-4">
                  <ResearchPanel
                    researchType="permit_explainer"
                    recordId={opp.id}
                    query={`New Orleans permit. Number: ${opp.permit_number || "(unknown)"}. Description: ${opp.permit_description || "(none)"}. Project type: ${opp.project_type || "(unknown)"}. Address: ${opp.project_address || "(unknown)"}. Explain in plain English what work this permit covers, typical scope + duration, and any red flags (historic district, structural, etc.).`}
                    label="Explain this permit"
                    hint="Plain-English breakdown of the permit + typical scope."
                    testId={`research-permit-${opp.id}`}
                  />
                </div>
              )}
            </section>

            <EditableDecisionPanel opp={opp} onUpdated={setOpp} />
          </div>

          {/* Right col: Activity */}
          <div className="space-y-6">
            <section
              className="bh-surface rounded-md p-5"
              data-testid="detail-relationships-preview"
            >
              <SectionHeading
                code="Section / 04"
                title="Relationships"
                hint="Not built yet"
              />
              {/* This panel used to show invented values ("1 possible via
                  Sarah Delatte", confidence "Low") next to real lead fields on
                  the page an operator decides from. Only the field names are
                  kept — no graph exists to populate them. */}
              <PreviewNotice
                testId="detail-relationships-notice"
                detail="No relationship graph is computed yet. These are the fields this panel will report; none of them influence the priority score or outreach eligibility."
              >
                <div className="space-y-2">
                  {[
                    { icon: User, label: "Direct relationship" },
                    { icon: Network, label: "Mutual connection" },
                    { icon: Building2, label: "Referral source" },
                    { icon: Signal, label: "Relationship confidence" },
                    { icon: Hammer, label: "Recommended intro path" },
                  ].map((r) => (
                    <div
                      key={r.label}
                      className="bh-surface-2 rounded p-3 flex items-center gap-3"
                    >
                      <div className="w-8 h-8 rounded bg-white/[0.03] border bh-hairline flex items-center justify-center">
                        <r.icon size={14} className="text-neutral-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
                          {r.label}
                        </div>
                        <div className="text-sm text-neutral-600">—</div>
                      </div>
                    </div>
                  ))}
                </div>
              </PreviewNotice>
            </section>

            <section className="bh-surface rounded-md p-5">
              <SectionHeading code="Section / 05" title="Activity Timeline" />
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
