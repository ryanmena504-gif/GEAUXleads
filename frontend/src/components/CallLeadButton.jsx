import React, { useState } from "react";
import { Phone } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { pickPhone } from "@/lib/contact";

/**
 * Call — rings Ryan's phone first, then connects him to the lead.
 * The lead sees the business number. This is bridge mode only.
 * Message mode stays on the API for a consented lead; the button
 * never starts an automated message.
 */

const OPT_OUT = /do not contact|do not call|opted out|opt out|\bdnc\b|unsubscribed/;

export const leadOptedOut = (opp) => {
  if (!opp) return false;
  const parts = [
    opp.status,
    opp.status_raw,
    opp.outreach_status,
    opp.approval_status,
    opp.hunt_status,
    opp.do_not_call,
    opp.dnc,
    opp.opt_out,
    opp.opted_out,
  ];
  const flags = opp.risk_flags;
  if (Array.isArray(flags)) parts.push(...flags);
  else if (flags) parts.push(flags);
  const blob = parts
    .filter((part) => part != null && part !== false)
    .join(" ")
    .toLowerCase()
    .replace(/[_-]/g, " ");
  if (OPT_OUT.test(blob)) return true;
  return opp.suppressed === true || opp.on_suppression_list === true;
};

export const callConfirmText = (opp) => {
  const who = String(opp?.decision_maker || opp?.name || "this lead").trim() || "this lead";
  const check = opp?.dnc_check_required
    ? "Check the Do Not Call list before calling this homeowner. "
    : "";
  return (
    `${check}Call ${who}? Your phone rings first, then we connect you. ` +
    "Their caller ID is the business number."
  );
};

const CallLeadButton = ({ opportunity, className = "" }) => {
  const [busy, setBusy] = useState(false);
  if (!pickPhone(opportunity) || leadOptedOut(opportunity)) return null;

  const place = async () => {
    if (!window.confirm(callConfirmText(opportunity))) return;
    setBusy(true);
    try {
      await api.callLead(opportunity.id, { mode: "bridge" });
      toast.success("Calling your phone now. Answer to be connected.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not place the call");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={place}
      disabled={busy}
      data-testid={`call-lead-${opportunity?.id || "unknown"}`}
      title="Rings your phone first, then connects you. Their caller ID is the business number."
      className={className}
    >
      <Phone size={13} />
      {busy ? "Calling…" : "Call"}
    </button>
  );
};

export default CallLeadButton;
