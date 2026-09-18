/**
 * Draft-safety guard — prevents raw AI prompts, unfilled template
 * placeholders, or empty machine output from ever reaching the send screen.
 *
 * These heuristics are conservative but explicit: if any of them trips,
 * OpenInMessages HIDES the mailto button and shows a visible error instead
 * of a "ready to send" draft. The trip must be a strong signal — false
 * positives block Ryan from mailing a real lead — so each pattern targets
 * text that a business recipient would never see in an actual outreach.
 *
 * A Python mirror lives in `backend/services/draft_safety.py`. Keep them in
 * sync when adding patterns.
 */

// Prompt-shaped openings. Anchored to the START of trimmed text so a normal
// sentence that happens to contain "You are" mid-body does not trip.
const PROMPT_OPENERS = [
  /^you are (a |an |the )/i,               // "You are a lead-research assistant..."
  /^you'?re (a |an |the )/i,
  /^please (enrich|pull|research|provide|generate|summarize|extract|analyze|classify|score)\b/i,
  /^i am (an? )?(ai|assistant|language model|claude|chatbot)\b/i,
  /^as an? (ai|assistant|language model)\b/i,
  /^\[(system|assistant|user|human|instructions?|prompt|role|task)\]/i,
  /^(system|assistant|user|human|instructions?|prompt|role|task)\s*[:—-]\s/i,
  /^###\s*(instructions?|role|task|context|prompt|system)/i,
];

// Structural markers anywhere in the body. Any single hit is a hard fail.
const STRUCTURAL_MARKERS = [
  /\{\{[^}]{1,80}\}\}/,                    // {{unfilled_placeholder}}
  /<<[A-Z_ ]{3,}>>/,                       // <<PLACEHOLDER>>
  /\bTODO\s*:\s*(fill|write|generate|complete|replace)/i,
  /\[(FILL|INSERT|REPLACE|TODO)\s*[^\]]*\]/i,   // [FILL IN MESSAGE]
  /\b(as an ai|as a language model|i'?m claude|i am claude)\b/i,
  /\bopenai\s+(gpt|api)/i,
];

// Empty / whitespace only. Body must have at least one real word char sequence
// of length 3 to be considered "has content". Trims quoted signatures.
const _MIN_WORD_CHARS = 3;

/**
 * looksLikeAIPrompt — returns { trip: boolean, reason: string|null }.
 * `text` is examined trimmed and case-insensitively for structural markers.
 * A "trip" means the text should NEVER be presented as a ready-to-send draft.
 */
export const looksLikeAIPrompt = (text) => {
  if (text == null) return { trip: true, reason: "empty" };
  const s = String(text).trim();
  if (!s) return { trip: true, reason: "empty" };
  // "Real content" floor — a draft with fewer than N alphanumeric chars is
  // almost certainly a stub. Signature-only bodies are handled by the caller
  // which only appends the signature AFTER this check.
  const wordChars = s.replace(/[^A-Za-z0-9]/g, "");
  if (wordChars.length < _MIN_WORD_CHARS) return { trip: true, reason: "too_short" };

  for (const re of PROMPT_OPENERS) {
    if (re.test(s)) return { trip: true, reason: "prompt_opener" };
  }
  for (const re of STRUCTURAL_MARKERS) {
    if (re.test(s)) return { trip: true, reason: "structural_marker" };
  }
  return { trip: false, reason: null };
};

/**
 * safeDraftBody — returns the trimmed body when it passes the guard, or
 * null when it trips. Callers should treat null as "do not render Send".
 */
export const safeDraftBody = (text) => {
  const { trip } = looksLikeAIPrompt(text);
  return trip ? null : String(text).trim();
};
