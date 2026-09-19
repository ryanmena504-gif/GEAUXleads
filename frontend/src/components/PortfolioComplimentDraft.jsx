import React from "react";
import { Mail, ShieldCheck, AlertTriangle, Lock } from "lucide-react";
import { useUserSettings } from "@/hooks/useUserSettings";
import { outreachAllowed } from "@/lib/queue";
import { buildSalutation } from "@/lib/greeting";
import { looksLikeAIPrompt } from "@/lib/draftSafety";
import { pickEmail, withSignature } from "@/components/OpenInMessages";

/**
 * PortfolioComplimentDraft — Slice 2 of Completed Project Proof.
 *
 * Opens the device-native email app with the Portfolio Check's compliment
 * line as the opening sentence, plus a short body + CTA + signature.
 *
 * Approval-only. Same guarantees as OpenInMessages:
 *   • Nothing sends. mailto: hands off to the device mail app.
 *   • No Airtable write. No status change. No score change.
 *   • No auto-follow-up. No booking link. No attachments.
 *
 * ELIGIBILITY GATES — ALL must pass or the button is disabled/hidden:
 *   1. `portfolio_compliment_line` populated
 *   2. `portfolio_check_confidence` is high OR medium (case-insensitive)
 *   3. `portfolio_project_status` is completed (case-insensitive)
 *   4. `portfolio_outreach_recommendation` is portfolio_opener OR
 *      use_project_opener (case + underscore tolerant)
 *   5. Verified public business email on the record (via pickEmail)
 *   6. Record is in Ready to Contact or Contacted queue (outreach allowed)
 *   7. The COMPOSED body passes `looksLikeAIPrompt` — belt-and-braces
 *      so a prompt-shaped Airtable value cannot leak into the mailto.
 *
 * If gates 1-4 pass but gate 5 fails (no email), the card shows a locked
 * "No verified email — draft disabled" state. This is the Slice 2
 * acceptance test #5 requirement: project proof may exist, but no email
 * draft may be generated without a verified public business email.
 */

const enc = encodeURIComponent;

const norm = (v) => (typeof v === "string" ? v.trim() : v);
const key = (v) => (typeof v === "string" ? v.trim().toLowerCase().replace(/[_\s]+/g, " ") : "");

const GREEN_RECS = new Set(["portfolio opener", "use project opener"]);

/**
 * Compose the mailto body from the compliment + partnership angle + a safe
 * hardcoded body + CTA + signature. Target the 65-110 word spec range from
 * the Slice 2 approval doc.
 */
export const buildPortfolioDraft = (opp, sender) => {
  const senderName = (sender?.sender_name || "Ryan Mena").trim();
  const salutation = buildSalutation(
    [opp?.decision_maker, opp?.contact_name],
    { verb: "Hi", generic: "there" },
  );
  const compliment = norm(opp?.portfolio_compliment_line) || "";
  const angle = norm(opp?.portfolio_partnership_angle) || "";
  // Body target ~65-110 words. Compliment (~15-25) + intro (~35-45) +
  // CTA (~15-20). If a partnership angle is present, prefer it as the
  // narrow offer; otherwise fall back to a generic finish-work line.
  const offerLine = angle
    ? `I'm ${senderName} with The Shirtless Handyman — a small specialty finish crew here in the New Orleans area. ${angle}`
    : `I'm ${senderName} with The Shirtless Handyman — a small specialty finish crew here in the New Orleans area, focused on microcement, lime plaster, waterproof grout-free showers, and similar detail work.`;
  const cta = "Not asking for anything today — just wanted to be on your radar for whenever a project calls for something in that lane. Happy to send examples or trade a coffee if you're open to it.";
  const body = [salutation, "", compliment, "", offerLine, "", cta].filter(Boolean).join("\n");
  const subject = opp?.portfolio_best_project_title
    ? `Loved the ${opp.portfolio_project_type || "project"} — quick note`
    : `Quick note from a local finish crew`;
  return {
    subject,
    body: withSignature(body, sender?.sender_name, sender?.sender_phone),
  };
};

const btnBase =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-semibold " +
  "transition-colors duration-150 whitespace-nowrap no-underline h-10 px-4 text-[13px]";

export const PortfolioComplimentDraft = ({ opportunity }) => {
  const { settings } = useUserSettings();

  const compliment = norm(opportunity?.portfolio_compliment_line);
  const confidence = key(opportunity?.portfolio_check_confidence);
  const projectStatus = key(opportunity?.portfolio_project_status);
  const recommendation = key(opportunity?.portfolio_outreach_recommendation);
  const email = pickEmail(opportunity);
  const outreach = outreachAllowed(opportunity);

  // Content gate — no compliment or unsafe classifiers means the button
  // has no legitimate content to offer. Render NOTHING in that case
  // (the card's own compliment suppression already told the user why).
  const contentGates = {
    hasCompliment: !!compliment,
    confidenceOk: confidence === "high" || confidence === "medium",
    statusOk: projectStatus === "completed",
    recommendationOk: GREEN_RECS.has(recommendation),
  };
  const contentReady =
    contentGates.hasCompliment
    && contentGates.confidenceOk
    && contentGates.statusOk
    && contentGates.recommendationOk;
  if (!contentReady) return null;

  // Delivery gate — content is safe to use, but do we have a legitimate
  // way to deliver it? If no email OR outreach isn't allowed on this
  // queue, show a LOCKED state so the operator sees the draft is
  // intentionally blocked rather than silently absent. (Slice 2 test #5.)
  const canDeliver = !!email && outreach !== "none";

  const senderIdentity = {
    sender_name: settings?.sender_name,
    sender_phone: settings?.sender_phone,
  };
  const draft = buildPortfolioDraft(opportunity, senderIdentity);
  // Final belt-and-braces safety re-check on the composed body.
  const finalCheck = looksLikeAIPrompt(draft.body);
  const bodyBlocked = finalCheck.trip;

  if (!canDeliver) {
    // Locked state. Content is safe; delivery isn't.
    const reason = !email
      ? "No verified email on this record."
      : "This record is in All Projects — the classifier hasn't approved outreach yet.";
    return (
      <div
        data-testid="portfolio-draft-locked"
        className="mt-3 rounded-md p-3 flex items-start gap-2 text-[12.5px] leading-relaxed"
        style={{
          background: "var(--bh-surface)",
          border: "1px solid var(--bh-hair)",
          color: "var(--bh-ink-2)",
        }}
        title="Portfolio draft is intentionally blocked — see reason."
      >
        <Lock size={12} className="mt-0.5 shrink-0" style={{ color: "var(--bh-ink-3)" }} />
        <span>
          <strong>Draft with portfolio compliment · disabled.</strong> {reason}
          {" "}Project proof stays visible above so you can act on it another way.
        </span>
      </div>
    );
  }

  if (bodyBlocked) {
    // Content passed but the composed body still tripped the safety guard.
    // Prevents any prompt-shaped compliment/angle text from reaching Send.
    return (
      <div
        data-testid="portfolio-draft-blocked"
        className="mt-3 rounded-md p-3 flex items-start gap-2 text-[12.5px] leading-relaxed"
        style={{
          background: "rgba(180,83,9,0.10)",
          border: "1px solid rgba(180,83,9,0.30)",
          color: "#d97706",
        }}
      >
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        <span>
          <strong>Draft blocked before it could reach Send.</strong> The
          compliment or partnership angle text looked like AI plumbing
          ({finalCheck.reason.replace(/_/g, " ")}) — safer to write this one
          by hand.
        </span>
      </div>
    );
  }

  const href = `mailto:${enc(email)}?subject=${enc(draft.subject)}&body=${enc(draft.body)}`;

  return (
    <div className="mt-3 flex items-center gap-2 flex-wrap">
      <a
        href={href}
        data-testid={`portfolio-draft-${opportunity?.id || "unknown"}`}
        className={btnBase}
        style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
      >
        <Mail size={13} strokeWidth={2} /> Draft with portfolio compliment
      </a>
      <span
        className="inline-flex items-center gap-1 text-[11px] text-[var(--bh-ink-3)]"
        data-testid="portfolio-draft-guarantee"
      >
        <ShieldCheck size={11} style={{ color: "var(--bh-olive)" }} />
        Opens a draft in your mail app · nothing sends until you press Send yourself.
      </span>
    </div>
  );
};

export default PortfolioComplimentDraft;
