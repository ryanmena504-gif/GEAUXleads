import React from "react";
import clsx from "clsx";
import {
  Phone,
  MessageSquare,
  Mail,
  Search,
  MapPin,
  FileText,
  Users,
  RotateCw,
  Clock,
} from "lucide-react";

/**
 * Next-move chip — muted, sentence-case, no alarm reds/oranges.
 * Every color reads as a material tone against the bone canvas.
 */
const cfg = {
  "Call Today":      { icon: Phone,        fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)",       border: "rgba(107,122,85,0.32)" },
  "Send Text":       { icon: MessageSquare,fg: "#4b6b6f",         bg: "rgba(75,107,111,0.10)",       border: "rgba(75,107,111,0.30)" },
  "Send Email":      { icon: Mail,         fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)",        border: "var(--bh-hair-warm)" },
  "Research First":  { icon: Search,       fg: "#7a6a4f",         bg: "rgba(122,106,79,0.12)",       border: "rgba(122,106,79,0.28)" },
  "Visit Property":  { icon: MapPin,       fg: "#8f6a3f",         bg: "rgba(143,106,63,0.10)",       border: "rgba(143,106,63,0.28)" },
  "Prepare Estimate":{ icon: FileText,     fg: "#5a5847",         bg: "rgba(90,88,71,0.12)",         border: "rgba(90,88,71,0.28)" },
  "Ask for Referral":{ icon: Users,        fg: "#6f6b56",         bg: "rgba(111,107,86,0.12)",       border: "rgba(111,107,86,0.28)" },
  "Follow Up":       { icon: RotateCw,     fg: "#6a5f52",         bg: "rgba(106,95,82,0.12)",        border: "rgba(106,95,82,0.28)" },
  Wait:              { icon: Clock,        fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)",     border: "var(--bh-hair)" },
};

export const MissionBadge = ({ mission, className, size = "md" }) => {
  const c = cfg[mission] || cfg.Wait;
  const Icon = c.icon;
  const sz = size === "sm" ? "text-[10.5px] px-2 py-0.5" : "text-[11.5px] px-2.5 py-1";
  return (
    <span
      data-testid={`mission-badge-${mission}`}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border font-medium tracking-tight",
        sz,
        className,
      )}
      style={{ color: c.fg, background: c.bg, borderColor: c.border }}
    >
      <Icon size={size === "sm" ? 11 : 12} strokeWidth={1.75} />
      {mission}
    </span>
  );
};

export default MissionBadge;
