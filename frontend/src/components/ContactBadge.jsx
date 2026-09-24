import React from "react";
import { CheckCircle2, AlertCircle, Eye, Ban } from "lucide-react";
import { contactState } from "@/lib/priority";

/**
 * ContactBadge — plain-English readiness signal in four colors:
 *   green  "Ready to contact"
 *   yellow "Needs a phone or email"
 *   gray   "Keep watching"
 *   red    "Not a fit"
 *
 * The component pulls state from the opportunity itself so pages don't
 * have to compute it inline.
 */
const STYLES = {
  green:  { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)", icon: CheckCircle2 },
  yellow: { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)",   icon: AlertCircle },
  gray:   { fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)",      icon: Eye },
  red:    { fg: "var(--bh-clay)", bg: "var(--bh-clay-mute)",   border: "rgba(165,90,62,0.28)", icon: Ban },
};

export const ContactBadge = ({ opportunity, size = "sm", className = "" }) => {
  const s = contactState(opportunity);
  const style = STYLES[s.color] || STYLES.gray;
  const Icon = style.icon;
  const sz = size === "md" ? "text-[11.5px] px-2.5 py-1" : "text-[10.5px] px-2 py-0.5";
  return (
    <span
      data-testid={`contact-badge-${s.key}`}
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium tracking-tight whitespace-nowrap ${sz} ${className}`}
      style={{ color: style.fg, background: style.bg, borderColor: style.border }}
    >
      <Icon size={size === "md" ? 12 : 11} strokeWidth={1.75} />
      {s.label}
    </span>
  );
};

export default ContactBadge;
