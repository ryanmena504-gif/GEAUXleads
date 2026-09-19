import React from "react";
import {
  ExternalLink,
  Sparkles,
  ShieldCheck,
  BookOpen,
  MessageSquareQuote,
  Handshake,
  AlertTriangle,
  Info,
} from "lucide-react";

/**
 * CompletedProjectProofCard — read-only surface for the Portfolio_*
 * fields Claude/Make writes via the Portfolio Check enrichment webhook.
 * Bloodhound never writes these fields; this component only renders.
 *
 * Safety rules (from `/app/memory/airtable_schema_round1.md`):
 *   • Render ONLY when at least one Portfolio_* field has a value.
 *   • Hide the Evidence link when `portfolio_best_project_url` is blank.
 *   • Label the link "Review source" (not "Evidence") when Confidence=Low
 *     OR Project Status=Unclear. A populated URL never authorizes a
 *     project-specific opener on its own.
 *   • Hide the Compliment Line whenever Confidence=Low OR Project
 *     Status=Unclear, even if Airtable holds a value.
 *   • Always surface: Confidence, Outreach Recommendation, Evidence
 *     Basis (locked to "Page text/captions" in Round 1), and — if
 *     present — Portfolio Found chip.
 *
 * All value comparisons are case-insensitive AND underscore-tolerant
 * because Claude/Make has shipped both `Portfolio Opener` and
 * `portfolio_opener` for the same field across runs. Safety must not
 * depend on which casing landed today.
 *
 * Zero writes from Bloodhound: no PATCH endpoint touches these fields.
 */

const norm = (v) => (typeof v === "string" ? v.trim() : v);
// Safety-critical: case-insensitive + underscore-tolerant key. `key("Low")`,
// `key("low")`, and `key("LOW")` all collapse to `"low"`. Used for every
// governed-value comparison in this card. NEVER compare display strings
// directly — always route through `key()`.
const key = (v) => (typeof v === "string" ? v.trim().toLowerCase().replace(/[_\s]+/g, " ") : "");
const isLowConfidence = (c) => key(c) === "low";
const isUnclearStatus = (s) => key(s) === "unclear";
// Display helper — capitalises the first letter of each word for chips
// so `"yes"` and `"Yes"` both render as "Yes". Purely cosmetic; the
// safety logic runs on `key()` regardless.
const titleCase = (v) => {
  if (typeof v !== "string") return v;
  const s = v.trim().replace(/[_]+/g, " ");
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
};

/** Any of the Portfolio_* fields populated → card renders. */
export const hasPortfolioData = (opp) => {
  if (!opp) return false;
  const keys = [
    "portfolio_found",
    "portfolio_best_project_title",
    "portfolio_best_project_url",
    "portfolio_project_type",
    "portfolio_project_status",
    "portfolio_business_role",
    "portfolio_evidence_summary",
    "portfolio_safe_observation",
    "portfolio_compliment_line",
    "portfolio_partnership_angle",
    "portfolio_check_confidence",
    "portfolio_outreach_recommendation",
    "portfolio_check_status",
    "portfolio_checked_at",
    "portfolio_evidence_basis",
    "portfolio_why_this_was_chosen",
    "portfolio_error_reason",
  ];
  return keys.some((k) => {
    const v = opp[k];
    return typeof v === "string" ? v.trim().length > 0 : v != null;
  });
};

const confidenceStyles = (c) => {
  const v = key(c);
  if (v === "high") return { fg: "#059669", bg: "rgba(5,150,105,0.10)", border: "rgba(5,150,105,0.30)" };
  if (v === "medium") return { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" };
  if (v === "low") return { fg: "#b45309", bg: "rgba(180,83,9,0.10)", border: "rgba(180,83,9,0.30)" };
  return { fg: "var(--bh-ink-3)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" };
};

const recommendationStyles = (r) => {
  const v = key(r);
  // Accept both the schema-doc option set AND Claude/Make's canonical
  // values (which drifted during Round 1 build and were retained by Ryan
  // 2026-02-19; runs since then have shipped both `Portfolio Opener` and
  // `portfolio_opener` casings). Case + underscore tolerant.
  if (v === "use project opener" || v === "portfolio opener") {
    return { fg: "#059669", bg: "rgba(5,150,105,0.10)", border: "rgba(5,150,105,0.30)" };
  }
  if (v === "use broad business opener" || v === "generic business opener") {
    return { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" };
  }
  if (v === "do not use") {
    return { fg: "#dc2626", bg: "rgba(220,38,38,0.10)", border: "rgba(220,38,38,0.30)" };
  }
  return { fg: "var(--bh-ink-3)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" };
};

const Chip = ({ label, value, style, testId }) => {
  if (!value) return null;
  return (
    <span
      data-testid={testId}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-tight"
      style={{ color: style.fg, background: style.bg, borderColor: style.border }}
    >
      <span className="mono text-[9px] uppercase tracking-widest opacity-75">{label}</span>
      <span>{value}</span>
    </span>
  );
};

const Field = ({ icon: Icon, label, children, testId }) => (
  <div data-testid={testId} className="space-y-1">
    <div className="bh-eyebrow inline-flex items-center gap-1.5">
      {Icon && <Icon size={11} strokeWidth={1.75} />}
      {label}
    </div>
    <div className="text-[14px] text-[var(--bh-ink-2)] leading-relaxed">
      {children}
    </div>
  </div>
);

export const CompletedProjectProofCard = ({ opportunity }) => {
  if (!hasPortfolioData(opportunity)) return null;
  const o = opportunity;

  const confidence = norm(o.portfolio_check_confidence);
  const projectStatus = norm(o.portfolio_project_status);
  const complimentUnsafe = isLowConfidence(confidence) || isUnclearStatus(projectStatus);

  const rawCompliment = norm(o.portfolio_compliment_line);
  const complimentLine = complimentUnsafe ? "" : rawCompliment;

  const url = norm(o.portfolio_best_project_url);
  const linkLabel = complimentUnsafe ? "Review source" : "Evidence";
  const linkTitle = complimentUnsafe
    ? "Attribution is unclear or confidence is low — inspect this source before quoting"
    : "Public source page the evidence was drawn from";

  const found = norm(o.portfolio_found);
  const foundStyle =
    key(found) === "yes"
      ? { fg: "#059669", bg: "rgba(5,150,105,0.10)", border: "rgba(5,150,105,0.30)" }
      : key(found) === "unclear"
        ? { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" }
        : { fg: "var(--bh-ink-3)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" };

  return (
    <section
      data-testid="portfolio-proof-card"
      className="bh-surface rounded-md p-5 border-t border-t-emerald-500/40"
    >
      {/* Failed-check banner — renders instead of the rest of the card
          when Claude/Make explicitly marked the run as Failed. Never
          shown when the check simply returned "No portfolio found".
          Case-insensitive so "Failed"/"failed" both trip. */}
      {key(o.portfolio_check_status) === "failed" && (
        <div
          data-testid="portfolio-check-failed"
          className="rounded-md p-3 mb-4 flex items-start gap-2"
          style={{
            background: "rgba(220,38,38,0.08)",
            border: "1px solid rgba(220,38,38,0.30)",
            color: "#dc2626",
          }}
        >
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <div className="text-[12.5px] leading-relaxed">
            <div className="font-medium">Portfolio check failed</div>
            {o.portfolio_error_reason && (
              <div className="mt-0.5 text-[var(--bh-ink-2)]">
                {o.portfolio_error_reason}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="bh-eyebrow inline-flex items-center gap-1.5">
            <Sparkles size={11} strokeWidth={1.75} /> Completed project proof
          </div>
          <h3 className="mt-1 font-display text-lg font-bold text-[var(--bh-ink)]">
            What we can honestly say about their work
          </h3>
          {o.portfolio_checked_at && (
            <div
              data-testid="portfolio-checked-at"
              className="mt-1 text-[11.5px] text-[var(--bh-ink-3)]"
            >
              Last checked · {new Date(o.portfolio_checked_at).toLocaleString(undefined, {
                dateStyle: "medium", timeStyle: "short",
              })}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <Chip label="Found" value={titleCase(found)} style={foundStyle} testId="portfolio-chip-found" />
          <Chip
            label="Confidence"
            value={titleCase(confidence)}
            style={confidenceStyles(confidence)}
            testId="portfolio-chip-confidence"
          />
          <Chip
            label="Recommendation"
            value={titleCase(o.portfolio_outreach_recommendation)}
            style={recommendationStyles(o.portfolio_outreach_recommendation)}
            testId="portfolio-chip-recommendation"
          />
        </div>
      </div>

      {/* Hero: Compliment Line — the field meant to drop straight into
          an outreach message. Suppressed when unsafe. */}
      {complimentLine ? (
        <div
          data-testid="portfolio-compliment-line"
          className="mt-4 rounded-md p-4"
          style={{ background: "var(--bh-brass-mute)", border: "1px solid var(--bh-hair-warm)" }}
        >
          <div className="bh-eyebrow inline-flex items-center gap-1.5" style={{ color: "var(--bh-brass)" }}>
            <MessageSquareQuote size={11} strokeWidth={1.75} /> Compliment line (ready to paste)
          </div>
          <p className="mt-2 text-[15px] leading-snug text-[var(--bh-ink)]">
            &ldquo;{complimentLine}&rdquo;
          </p>
        </div>
      ) : (
        rawCompliment && complimentUnsafe && (
          <div
            data-testid="portfolio-compliment-suppressed"
            className="mt-4 rounded-md p-3 text-[12.5px] leading-relaxed flex items-start gap-2"
            style={{
              background: "rgba(180,83,9,0.08)",
              border: "1px solid rgba(180,83,9,0.25)",
              color: "#d97706",
            }}
          >
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            <span>
              Compliment line hidden — {isLowConfidence(confidence) ? "confidence is Low" : "project status is Unclear"}.
              Do not use a project-specific opener on this record. Open the source below to review the evidence yourself.
            </span>
          </div>
        )
      )}

      {/* Evidence link + project title */}
      {(o.portfolio_best_project_title || url) && (
        <div className="mt-4 space-y-1" data-testid="portfolio-best-project">
          {o.portfolio_best_project_title && (
            <div className="text-[15px] font-medium text-[var(--bh-ink)] leading-snug">
              {o.portfolio_best_project_title}
            </div>
          )}
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer noopener"
              data-testid="portfolio-evidence-link"
              title={linkTitle}
              className="inline-flex items-center gap-1.5 text-[12.5px] font-medium"
              style={{ color: complimentUnsafe ? "#d97706" : "var(--bh-brass)" }}
            >
              <ExternalLink size={12} strokeWidth={1.75} /> {linkLabel}
              <span className="text-[11px] text-[var(--bh-ink-3)] font-normal ml-1 truncate max-w-[280px]">
                {url}
              </span>
            </a>
          )}
        </div>
      )}

      <div className="mt-4 grid md:grid-cols-2 gap-5">
        {o.portfolio_evidence_summary && (
          <Field
            icon={BookOpen}
            label="Evidence summary"
            testId="portfolio-evidence-summary"
          >
            {o.portfolio_evidence_summary}
          </Field>
        )}
        {o.portfolio_safe_observation && (
          <Field
            icon={ShieldCheck}
            label="Safe observation"
            testId="portfolio-safe-observation"
          >
            {o.portfolio_safe_observation}
          </Field>
        )}
        {o.portfolio_partnership_angle && (
          <Field
            icon={Handshake}
            label="Partnership angle"
            testId="portfolio-partnership-angle"
          >
            {o.portfolio_partnership_angle}
          </Field>
        )}
        {o.portfolio_why_this_was_chosen && (
          <Field
            icon={Info}
            label="Why this was chosen"
            testId="portfolio-why-chosen"
          >
            {o.portfolio_why_this_was_chosen}
          </Field>
        )}
      </div>

      <div className="mt-4 flex items-center gap-3 flex-wrap text-[11px] text-[var(--bh-ink-3)]">
        {o.portfolio_project_type && (
          <span data-testid="portfolio-project-type">
            <span className="mono uppercase tracking-widest opacity-70 mr-1">Project type</span>
            {o.portfolio_project_type}
          </span>
        )}
        {projectStatus && (
          <span data-testid="portfolio-project-status">
            <span className="mono uppercase tracking-widest opacity-70 mr-1">Status</span>
            {projectStatus}
          </span>
        )}
        {o.portfolio_business_role && (
          <span data-testid="portfolio-business-role">
            <span className="mono uppercase tracking-widest opacity-70 mr-1">Role</span>
            {o.portfolio_business_role}
          </span>
        )}
        <span data-testid="portfolio-evidence-basis" className="inline-flex items-center gap-1">
          <Info size={10} strokeWidth={1.75} />
          <span className="mono uppercase tracking-widest opacity-70">Evidence basis</span>
          <span>{norm(o.portfolio_evidence_basis) || "Page text/captions only"}</span>
        </span>
      </div>
    </section>
  );
};

export default CompletedProjectProofCard;
