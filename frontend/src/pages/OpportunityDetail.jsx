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
import { api } from "@/lib/api";
import { fmtMoney, fmtMoneyFull, fmtDate, fmtDateTime, sourceLabel } from "@/lib/formatters";
import { needsConfirmation } from "@/lib/priority";
import {
  ArrowLeft,
  MapPin,
  Phone,
  Mail,
  FileText,
  ShieldAlert,
  Info,
  Search,
  Clock3,
  CheckCircle2,
  Send,
  ClipboardList,
  Trophy,
  XCircle,
  Gauge,
  Target,
  PenLine,
  AlertTriangle,
  Sparkles,
} from "lucide-react";

// Five manual result buttons — Ryan taps AFTER a real-world action.
// Opening a draft never touches these; only a deliberate tap sends the
// result to Airtable via /api/opportunities/{id}/result.
const RESULT_BUTTONS = [
  { label: "I sent it",          result: "sent",               icon: Send,          tone: "primary" },
  { label: "They replied",       result: "replied",            icon: CheckCircle2,  tone: "success" },
  { label: "Estimate requested", result: "estimate_requested", icon: ClipboardList, tone: "ghost" },
  { label: "No reply yet",       result: "no_reply",           icon: Search,        tone: "ghost" },
  { label: "Not interested",     result: "not_interested",     icon: XCircle,       tone: "danger" },
];

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
            key={i}
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
  const [enriching, setEnriching] = useState(false);

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

  const handleResult = async (result, label) => {
    setBusy(result);
    try {
      const res = await api.recordResult(id, result);
      if (res?.opportunity) setOpp(res.opportunity);
      toast.success(`Saved: ${label}`);
    } catch (e) {
      const msg = e?.response?.data?.detail || "Could not save result";
      toast.error(msg);
    } finally {
      setBusy(null);
    }
  };

  const handleFindContact = async () => {
    if (enriching) return;
    setEnriching(true);
    toast.info("Searching for public contact info…");
    try {
      const res = await api.enrichLead(id);
      if (res?.opportunity) setOpp(res.opportunity);
      const r = res?.result || {};
      const found = [];
      if (r.phone) found.push("phone");
      if (r.email) found.push("email");
      if (r.website) found.push("website");
      if (found.length) {
        toast.success(`Found: ${found.join(", ")}`);
      } else {
        toast.warning("Nothing publicly verifiable was found for this lead.");
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || "Enrichment failed";
      toast.error(msg);
    } finally {
      setEnriching(false);
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

        {/* Needs confirmation — Airtable history says something was sent but
            Ryan never tapped a result button. Prompt him to resolve. */}
        {needsConfirmation(opp) && (
          <div
            data-testid="needs-confirmation-banner"
            className="rounded-md border p-4 flex items-start gap-3"
            style={{
              background: "var(--bh-brass-mute)",
              borderColor: "var(--bh-hair-warm)",
              color: "var(--bh-brass)",
            }}
          >
            <AlertTriangle size={16} strokeWidth={1.75} className="shrink-0 mt-0.5" />
            <div className="text-[13.5px] leading-relaxed">
              <div className="font-medium">Needs confirmation</div>
              <div className="text-[12.5px] text-[var(--bh-ink-2)] mt-0.5">
                The record shows outreach history, but nothing has been
                confirmed. Tap one of the result buttons below (I sent it,
                They replied, No reply yet, etc.) to keep the tracker honest.
              </div>
            </div>
          </div>
        )}

        {/* Hero */}
        <section
          data-testid="opp-hero"
          className="bh-surface rounded-md p-5 lg:p-6 border-t border-t-amber-500/60"
        >
          <div className="grid lg:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <StatusBadge status={opp.status} />
                <PriorityBand band={opp.priority_band} score={opp.priority_score} />
              </div>
              <h1 className="mt-2 font-display text-3xl lg:text-4xl font-bold text-[var(--bh-ink)] tracking-tight">
                {opp.name}
              </h1>
              <div className="mt-2 flex items-center gap-2 text-sm text-[var(--bh-ink-mute)]">
                <MapPin size={14} className="text-[var(--bh-ink-mute)]" />
                {opp.project_address}
              </div>
              <div className="mt-4 grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4 min-w-0">
                <div>
                  <div className="bh-eyebrow">
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
                  <div className="bh-eyebrow">
                    Possible work value
                  </div>
                  <div className="font-display text-2xl lg:text-3xl font-bold text-[var(--bh-ink)] tabular-nums mt-1">
                    {fmtMoney(opp.estimated_value)}
                  </div>
                </div>
                <div>
                  <div className="bh-eyebrow">
                    Found on
                  </div>
                  <div className="mt-1 text-[var(--bh-ink)] font-medium">
                    {sourceLabel(opp.source)}
                  </div>
                </div>
                <div>
                  <div className="bh-eyebrow">
                    Project type
                  </div>
                  <div className="mt-1 text-[var(--bh-ink)] font-medium">
                    {opp.project_type}
                  </div>
                </div>
              </div>
            </div>

            {/* Primary action panel */}
            <div className="bh-surface-2 rounded p-4 min-w-0">
                <div className="bh-eyebrow">
                  What to do next
                </div>
                <div className="mt-1.5">
                  <MissionBadge mission={opp.daily_mission} />
                </div>
                <div className="mt-3 font-display text-lg font-semibold text-[var(--bh-ink)] leading-snug">
                  {opp.recommended_action}
                </div>
                <div className="mt-2 text-sm text-amber-200/90">
                  → {opp.next_best_action}
                </div>

              <div className="mt-4 border-t bh-hairline pt-3 space-y-2">
                <OpenInMessages opportunity={opp} variant="panel" />
                <div className="space-y-1.5 pt-1">
                {RESULT_BUTTONS.map((a) => {
                  return (
                    <button
                      key={a.result}
                      data-testid={`result-${a.result}`}
                      disabled={busy === a.result}
                      onClick={() => handleResult(a.result, a.label)}
                      className={
                        "w-full flex items-center gap-2 px-3 h-9 rounded text-sm transition-colors duration-150 " +
                        (a.tone === "primary"
                          ? "bg-amber-500 text-neutral-950 hover:bg-amber-400 font-medium"
                          : a.tone === "success"
                            ? "border bh-hairline text-emerald-300 hover:bg-emerald-500/10"
                            : a.tone === "danger"
                              ? "border bh-hairline text-red-300 hover:bg-red-500/10"
                              : "border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)]") +
                        " disabled:cursor-not-allowed disabled:opacity-50"
                      }
                    >
                      <a.icon size={14} />
                      {a.label}
                    </button>
                  );
                })}
                <p className="text-[11px] text-[var(--bh-ink-3)] leading-relaxed pt-1">
                  Only tap these after you personally sent, received a reply,
                  or heard back. Opening a draft never records anything.
                </p>
                {opp.lane === "partner" && (
                  <button
                    type="button"
                    onClick={() => setDraftOpen(true)}
                    data-testid="action-draft-note"
                    className="w-full flex items-center gap-2 px-3 h-9 rounded text-sm border transition-colors duration-150 mt-3"
                    style={{
                      background: "var(--bh-brass-mute)",
                      borderColor: "var(--bh-hair-warm)",
                      color: "var(--bh-brass)",
                    }}
                  >
                    <PenLine size={14} />
                    Draft a note
                  </button>
                )}
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
                          key={i}
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
                          key={i}
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

              <div className="mt-5 grid grid-cols-2 sm:grid-cols-5 gap-4">
                <Meter label="Opportunity Fit" level={opp.opportunity_fit} />
                <Meter label="Momentum" level={opp.momentum} />
                <Meter label="Reachability" level={opp.reachability} />
                <Meter label="Can I reach them?" level={opp.contact_confidence} />
                <Meter label="How solid is the info" level={opp.evidence_confidence} />
              </div>
            </section>

            {/* Contact */}
            <section className="bh-surface rounded-md p-5">
              <div className="flex items-baseline justify-between mb-3 gap-3">
                <h3 className="font-display text-lg font-bold text-[var(--bh-ink)]">
                  Who to talk to
                </h3>
                {!opp.phone && !opp.email && (
                  <button
                    type="button"
                    onClick={handleFindContact}
                    disabled={enriching}
                    data-testid="find-contact-btn"
                    className="text-[12.5px] h-8 px-3 rounded-md font-medium inline-flex items-center gap-1.5 border transition-colors duration-150 disabled:opacity-50"
                    style={{
                      background: "var(--bh-brass-mute)",
                      borderColor: "var(--bh-hair-warm)",
                      color: "var(--bh-brass)",
                    }}
                  >
                    <Sparkles size={13} />
                    {enriching ? "Searching…" : "Find contact"}
                  </button>
                )}
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
                    <li key={i} className="relative">
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
