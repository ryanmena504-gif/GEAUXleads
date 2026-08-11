import React from "react";
import { Mail, Phone } from "lucide-react";

const ContactBadge = ({ opportunity }) => {
  const hasPhone = Boolean(opportunity?.contact_phone || opportunity?.phone);
  const hasEmail = Boolean(opportunity?.contact_email || opportunity?.email);
  const label = hasPhone || hasEmail ? "Ready to contact" : "Needs public contact";

  return (
    <span
      data-testid={`contact-badge-${opportunity?.id || "unknown"}`}
      className={
        "inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium " +
        (hasPhone || hasEmail
          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
          : "border-neutral-500/25 bg-neutral-500/10 text-neutral-400")
      }
    >
      {hasPhone ? <Phone size={11} /> : hasEmail ? <Mail size={11} /> : null}
      {label}
    </span>
  );
};

export default ContactBadge;
