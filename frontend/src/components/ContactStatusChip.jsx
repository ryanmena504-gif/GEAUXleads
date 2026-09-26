import React from "react";
import { Mail, Phone, Search, Sparkles, Circle } from "lucide-react";

/**
 * Renders one of six contact-status chips derived purely from existing
 * DTO fields. No backend call; no fabrication.
 */
export const ContactStatusChip = ({ record, twilioEnabled = false, testId }) => {
  const hasEmail = Boolean((record?.email || record?.email_alt || "").toString().trim());
  const hasPhone = Boolean((record?.phone || record?.phone_alt || "").toString().trim());
  const isReAgent = record?._feed === "re_agents";

  let variant;
  if (hasEmail && hasPhone) variant = "both";
  else if (hasEmail) variant = "email";
  else if (hasPhone) variant = "phone";
  else if (isReAgent) variant = "autofill";
  else if (twilioEnabled && hasPhone) variant = "lookup";
  else variant = "none";

  const CFG = {
    both:     { icon: [Mail, Phone], label: "Both on file",     color: "#5b7a4a", bg: "rgba(91,122,74,0.12)" },
    email:    { icon: [Mail],        label: "Email only",       color: "#3f6b6b", bg: "rgba(63,107,107,0.12)" },
    phone:    { icon: [Phone],       label: "Phone only",       color: "#3f6b6b", bg: "rgba(63,107,107,0.12)" },
    lookup:   { icon: [Search],      label: "Lookup ready",     color: "#6a5a8a", bg: "rgba(106,90,138,0.12)" },
    autofill: { icon: [Sparkles],    label: "Auto-fill eligible", color: "#8a6a3f", bg: "rgba(191,150,90,0.14)" },
    none:     { icon: [Circle],      label: "No contact yet",   color: "#8a5a45", bg: "rgba(138,90,69,0.10)" },
  };
  const c = CFG[variant];
  return (
    <span
      data-testid={testId || `contact-status-${variant}`}
      data-variant={variant}
      className="inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[10.5px] font-medium tabular-nums whitespace-nowrap"
      style={{ color: c.color, background: c.bg }}
    >
      {c.icon.map((I, i) => (
        <I key={i} size={9} strokeWidth={2} />
      ))}
      <span className="ml-0.5">{c.label}</span>
    </span>
  );
};

export default ContactStatusChip;
