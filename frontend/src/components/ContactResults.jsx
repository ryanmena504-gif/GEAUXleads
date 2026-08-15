import React, { useState } from "react";
import { Check, MessageCircle, ClipboardList, XCircle, Clock3 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const RESULT_ACTIONS = [
  { event: "sent", label: "I sent it", icon: Check, tone: "primary" },
  { event: "replied", label: "They replied", icon: MessageCircle, tone: "plain" },
  { event: "estimate_requested", label: "Estimate requested", icon: ClipboardList, tone: "plain" },
  { event: "no_response", label: "No reply yet", icon: Clock3, tone: "plain" },
  { event: "not_interested", label: "Not interested", icon: XCircle, tone: "plain" },
];

const ContactResults = ({ opportunity, onSaved }) => {
  const [busy, setBusy] = useState("");
  const options = [
    ...(opportunity?.contact_phone || opportunity?.phone ? ["Text"] : []),
    ...(opportunity?.contact_email || opportunity?.email ? ["Email"] : []),
  ];
  const [channel, setChannel] = useState(options[0] || "Other");

  const save = async (event) => {
    const action = RESULT_ACTIONS.find((item) => item.event === event);
    if (!action) return;
    if (event === "sent" && !window.confirm("Only record this after you pressed Send yourself. Did you send it?")) {
      return;
    }
    setBusy(event);
    try {
      const updated = await api.recordResult(opportunity.id, { event, channel });
      onSaved?.(updated);
      toast.success(
        event === "sent" ? "Saved as sent" :
        event === "replied" ? "Reply saved" :
        event === "estimate_requested" ? "Estimate request saved" :
        event === "not_interested" ? "Marked not interested" :
        "Saved as no reply yet",
      );
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not save that result");
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="border-t bh-hairline pt-3 space-y-2" data-testid="contact-results">
      <div className="bh-eyebrow">After you do something</div>
      <p className="text-[12px] leading-relaxed text-[var(--bh-ink-3)]">
        Opening a draft does not count as contact. Tap one of these only after something actually happened.
      </p>
      {options.length > 1 && (
        <div className="flex items-center gap-1.5" aria-label="Choose how you contacted them">
          <span className="text-[11px] text-[var(--bh-ink-mute)]">I used:</span>
          {options.map((option) => (
            <button
              key={option}
              type="button"
              data-testid={`result-channel-${option.toLowerCase()}-${opportunity?.id}`}
              onClick={() => setChannel(option)}
              className={
                "rounded-full px-2.5 py-1 text-[11px] border transition-colors " +
                (channel === option
                  ? "bg-[var(--bh-brass-mute)] border-[var(--bh-hair-warm)] text-[var(--bh-brass)]"
                  : "bh-hairline text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)]")
              }
            >
              {option}
            </button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {RESULT_ACTIONS.map((item) => (
          <button
            key={item.event}
            type="button"
            data-testid={`result-${item.event}-${opportunity?.id}`}
            onClick={() => save(item.event)}
            disabled={busy === item.event}
            className={
              "min-h-9 px-3 rounded-md text-[12px] inline-flex items-center gap-1.5 border transition-colors disabled:opacity-50 " +
              (item.tone === "primary"
                ? "bg-amber-500 text-neutral-950 border-amber-400 font-medium hover:bg-amber-400"
                : "bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)]")
            }
          >
            <item.icon size={13} />
            {busy === item.event ? "Saving…" : item.label}
          </button>
        ))}
      </div>
    </section>
  );
};

export default ContactResults;
