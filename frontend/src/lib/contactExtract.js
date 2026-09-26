/**
 * Extract a plausible email address and US phone number from a chunk
 * of Perplexity's free-text answer. Regex-based on purpose — small,
 * dependency-free, and always returns strings the operator can review
 * before writing to Airtable. Never fabricates: if the answer doesn't
 * clearly contain a match, returns null for that field.
 */

// Simple RFC-shaped email pattern. Deliberately loose on the local
// part (per RFC 5321) and strict on requiring a dot in the domain.
const EMAIL_RE = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;

// Match: 504-517-6533, (504) 517-6533, 504.517.6533, +1 504 517 6533,
// 5045176533. Reject anything without exactly 10 digits (US) or 11 with
// leading 1.
const PHONE_RE = /(?:\+?1[\s.\-]?)?\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})/g;

// Emails Perplexity/models occasionally fabricate as placeholders —
// silently drop them so the operator doesn't paste noise into Airtable.
const EMAIL_DENYLIST = new Set([
  "example@example.com",
  "test@example.com",
  "info@example.com",
  "someone@example.com",
]);

export const extractEmail = (text) => {
  if (!text || typeof text !== "string") return null;
  const matches = text.match(EMAIL_RE) || [];
  for (const raw of matches) {
    const email = raw.trim().toLowerCase();
    if (EMAIL_DENYLIST.has(email)) continue;
    if (email.endsWith(".example") || email.endsWith(".test")) continue;
    return email;
  }
  return null;
};

export const extractPhone = (text) => {
  if (!text || typeof text !== "string") return null;
  const seen = new Set();
  let m;
  PHONE_RE.lastIndex = 0;
  while ((m = PHONE_RE.exec(text)) !== null) {
    const digits = `${m[1]}${m[2]}${m[3]}`;
    if (digits.length !== 10) continue;
    // Reject 555-01xx (reserved for fiction) and 000/111/222… repeats.
    if (m[1] === "555" && m[2].startsWith("01")) continue;
    if (/^(\d)\1{9}$/.test(digits)) continue;
    if (seen.has(digits)) continue;
    seen.add(digits);
    return `(${m[1]}) ${m[2]}-${m[3]}`;
  }
  return null;
};

export const extractContact = (text) => ({
  email: extractEmail(text),
  phone: extractPhone(text),
});
