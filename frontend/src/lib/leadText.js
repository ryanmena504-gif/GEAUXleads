/**
 * The text the lead UI shows before it sends. The server adds the same
 * STOP line if a script posts a body without it.
 */
import { looksLikeAIPrompt } from "./draftSafety";
import { buildSalutation } from "./greeting";

export const STOP_LINE = "Reply STOP to opt out";

const STOP_RE = /reply\s+stop\s+to\s+opt\s+out/i;

export const withStopLine = (body) => {
  const text = String(body || "").trim();
  if (STOP_RE.test(text)) return text;
  return text ? `${text}\n\n${STOP_LINE}` : STOP_LINE;
};

const defaultText = (opp) => {
  const hello = buildSalutation(
    [opp?.decision_maker, opp?.contact_name],
    { verb: "Hi", generic: "there", email: opp?.email || opp?.contact_email },
  ).replace(/,\s*$/, "");
  return `${hello} — Ryan at The Shirtless Handyman. Thanks for writing back. What time works for a quick call?`;
};

export const leadTextBody = (opp) => {
  const stored = String(
    opp?.draft_outreach_body || opp?.first_message || opp?.first_contact_message || "",
  ).trim();
  const safe = stored && !looksLikeAIPrompt(stored).trip ? stored : "";
  return withStopLine(safe || defaultText(opp));
};
