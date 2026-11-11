/**
 * Which phone and email to show or send.
 *
 * Contact phone and Contact email are the columns that hold the real
 * values. Phone number and Email are the old columns and are empty on
 * the live lead list. Read the Contact columns first. Use the old
 * columns only when the Contact columns are blank.
 *
 * The two API shapes use different key names for the same columns, so
 * every reader goes through this list instead of picking one key.
 */

export const PHONE_KEYS = ["contact_phone", "phone", "phone_number", "phone_alt"];
export const EMAIL_KEYS = ["contact_email", "email", "email_alt"];

const filled = (value) => {
  const text = (value ?? "").toString().trim();
  return text || "";
};

export const firstFilled = (record, keys) => {
  if (!record) return "";
  for (const key of keys) {
    const text = filled(record[key]);
    if (text) return text;
  }
  return "";
};

export const pickPhone = (record) => firstFilled(record, PHONE_KEYS);

/** An address containing @, or null when none of the email columns has one. */
export const pickEmail = (record) => {
  const raw = firstFilled(record, EMAIL_KEYS);
  return raw.includes("@") ? raw : null;
};

/** True when any phone or email column has something in it. */
export const hasContactChannel = (record) =>
  Boolean(firstFilled(record, PHONE_KEYS) || firstFilled(record, EMAIL_KEYS));
