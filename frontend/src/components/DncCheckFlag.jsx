import React from "react";
import { PhoneOff } from "lucide-react";

/**
 * Visible reminder on a homeowner phone. Research tags the contact
 * source; this does not dial, text, or look the number up on a registry.
 */
export const DncCheckFlag = ({ opp, testId }) => {
  if (!opp?.dnc_check_required) return null;
  return (
    <div
      role="note"
      data-testid={testId || `dnc-check-${opp.id || "lead"}`}
      className="flex items-start gap-2 rounded-md border px-3 py-2 text-[12.5px] leading-snug"
      style={{
        borderColor: "rgba(138,90,69,0.45)",
        background: "rgba(138,90,69,0.10)",
        color: "#8a5a45",
      }}
    >
      <PhoneOff size={14} className="mt-0.5 shrink-0" />
      <span>Check the Do Not Call list before calling or texting this homeowner number.</span>
    </div>
  );
};

export const ContactSourceChip = ({ opp }) => {
  const source = opp?.contact_source;
  if (source !== "homeowner" && source !== "business") return null;
  const homeowner = source === "homeowner";
  return (
    <span
      data-testid={`contact-source-${opp.id || "lead"}`}
      className="inline-flex items-center rounded-full px-2 py-[2px] text-[10.5px] font-medium"
      style={{
        color: homeowner ? "#8a5a45" : "#3f6b6b",
        background: homeowner ? "rgba(138,90,69,0.12)" : "rgba(63,107,107,0.12)",
      }}
    >
      {homeowner ? "Homeowner" : "Business contact"}
    </span>
  );
};

export default DncCheckFlag;
