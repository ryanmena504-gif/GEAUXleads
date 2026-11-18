/**
 * CAN-SPAM lines for a cold email. Mirror of backend/services/canspam.py.
 *
 * The postal address is REACT_APP_BUSINESS_MAILING_ADDRESS, baked in at
 * build time. When it is unset, the draft shows a placeholder. No street
 * address is written here.
 */

export const ADDRESS_ENV = "REACT_APP_BUSINESS_MAILING_ADDRESS";
export const ADDRESS_PLACEHOLDER = "[physical address — set BUSINESS_MAILING_ADDRESS]";
const MARKER = 'reply "unsubscribe"';

export const businessMailingAddress = () => {
  const raw = (process.env.REACT_APP_BUSINESS_MAILING_ADDRESS || "").trim();
  return raw || ADDRESS_PLACEHOLDER;
};

export const canSpamFooter = () =>
  [
    "The Shirtless Handyman",
    businessMailingAddress(),
    "",
    'If you\'d rather not get these emails, reply "unsubscribe" and I\'ll take you off the list.',
  ].join("\n");

/** Append the footer once. A body that already opts out is left alone. */
export const withCanSpam = (body) => {
  const base = (body || "").trim();
  if (base.toLowerCase().includes(MARKER)) return base;
  const footer = canSpamFooter();
  return base ? `${base}\n\n${footer}` : footer;
};
