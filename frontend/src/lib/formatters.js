export const fmtMoney = (v) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${n.toLocaleString()}`;
};

export const fmtMoneyFull = (v) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  return `$${n.toLocaleString()}`;
};

// A missing or zero estimate is not a zero-dollar job. Bloodhound uses zero
// when the public record or AI does not support a responsible estimate.
export const fmtMoneyOrStatus = (v, unavailableLabel) => {
  if (v === null || v === undefined || v === "") return unavailableLabel;
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return unavailableLabel;
  return fmtMoney(v);
};

/**
 * moneyDisplay — the single money renderer for opportunity cards + detail.
 *
 *   • If `estimated_value` is a positive number → format as $NK / $N.NM.
 *   • Else fall back to Airtable's formula strings that Ryan already sees
 *     inside Airtable: `Estimated opportunity value` (e.g. "Not estimated
 *     yet") or `Official project value` (e.g. "Not public"), or the
 *     `Revenue potential` bucket ("$5k-15k").
 *   • Else return null so the UI can hide the badge entirely.
 *
 * Never invents a value. When the app and Airtable disagree, it defers to
 * Airtable.
 */
export const moneyDisplay = (opp) => {
  if (!opp) return null;
  const n = Number(opp.estimated_value);
  if (Number.isFinite(n) && n > 0) return fmtMoney(n);
  const candidates = [
    opp.opportunity_value_display,
    opp.official_project_value,
    opp.revenue_potential,
  ];
  for (const c of candidates) {
    if (typeof c === "string" && c.trim()) return c.trim();
    if (typeof c === "number" && c > 0) return fmtMoney(c);
  }
  return null;
};

export const fmtDate = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch (e) {
    return "—";
  }
};

export const fmtDateTime = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch (e) {
    return "—";
  }
};

export const fmtRelative = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const day = 86_400_000;
    if (diff < 60_000) return "just now";
    if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
    if (diff < day) return `${Math.round(diff / 3_600_000)}h ago`;
    if (diff < 7 * day) return `${Math.round(diff / day)}d ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "—";
  }
};

export const sourceLabel = (s) =>
  ({
    permit: "Permit",
    website: "Website",
    referral: "Referral",
    nextdoor: "Nextdoor",
    google_places: "Google Places",
    manual: "Manual entry",
  })[s] || s || "—";
