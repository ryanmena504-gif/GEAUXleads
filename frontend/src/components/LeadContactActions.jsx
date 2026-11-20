import React, { useEffect, useState } from "react";
import { MessageSquare, Phone } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { pickPhone } from "@/lib/contact";
import { leadTextBody, withStopLine } from "@/lib/leadText";

const btn =
  "inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-[12.5px] font-medium border bh-hairline text-[var(--bh-ink-2)] hover:text-[var(--bh-ink)] hover:bg-white/[0.03] transition-colors disabled:opacity-60";
const quiet =
  "inline-flex items-center h-9 px-1 text-[12px] text-[var(--bh-ink-3)] underline underline-offset-2 hover:text-[var(--bh-ink)]";

const errorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message) {
    return detail.message;
  }
  if (typeof detail === "string") return detail;
  return fallback;
};

/**
 * Call and Text for one lead.
 *
 * Call uses bridge mode: Ryan's phone rings, then the lead, with the shop
 * number on their caller ID. Text sends through the API after the message
 * is on screen. Open on phone is the old sms: link.
 */
export const LeadContactActions = ({ opportunity }) => {
  const id = opportunity?.id;
  const phone = pickPhone(opportunity);
  const message = leadTextBody(opportunity);
  const [callOpen, setCallOpen] = useState(false);
  const [textOpen, setTextOpen] = useState(false);
  const [draft, setDraft] = useState(message);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(message);
  }, [message]);

  if (!id || !phone) return null;

  const smsPhone = phone.replace(/[^\d+]/g, "");
  const smsBody = withStopLine(textOpen ? draft : message);
  const smsHref = smsPhone ? `sms:${smsPhone}?body=${encodeURIComponent(smsBody)}` : null;

  const placeCall = async () => {
    setBusy("call");
    setError("");
    try {
      await api.callLead(id, "bridge");
      toast.success("Calling your phone. Pick up and we'll connect you.");
      setCallOpen(false);
    } catch (err) {
      const msg = errorMessage(err, "Couldn't place the call.");
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy("");
    }
  };

  const sendText = async () => {
    const body = withStopLine(draft);
    setDraft(body);
    setBusy("text");
    setError("");
    try {
      await api.textLead(id, body);
      toast.success("Text sent.");
      setTextOpen(false);
    } catch (err) {
      const msg = errorMessage(err, "Couldn't send the text.");
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid={`lead-contact-${id}`}>
      <button
        type="button"
        className={btn}
        data-testid={`call-lead-${id}`}
        disabled={busy === "call"}
        onClick={() => {
          setTextOpen(false);
          setError("");
          setCallOpen((open) => !open);
        }}
      >
        <Phone size={13} /> {busy === "call" ? "Calling…" : "Call"}
      </button>
      <button
        type="button"
        className={btn}
        data-testid={`text-lead-${id}`}
        disabled={busy === "text"}
        onClick={() => {
          setCallOpen(false);
          setError("");
          setTextOpen((open) => !open);
        }}
      >
        <MessageSquare size={13} /> {busy === "text" ? "Sending…" : "Text"}
      </button>
      {smsHref && (
        <a href={smsHref} className={quiet} data-testid={`open-on-phone-${id}`}>
          Open on phone
        </a>
      )}
      {callOpen && (
        <div className="basis-full rounded-md border bh-hairline p-3 space-y-2" data-testid={`call-lead-confirm-${id}`}>
          <p className="text-[13px] text-[var(--bh-ink-2)]">
            Your phone rings first. When you answer, we connect you. They see the shop number.
          </p>
          <div className="flex gap-2">
            <button type="button" className={btn} onClick={placeCall} disabled={busy === "call"} data-testid={`call-lead-now-${id}`}>
              Call now
            </button>
            <button type="button" className={btn} onClick={() => setCallOpen(false)}>
              Cancel
            </button>
          </div>
          {error && (
            <p className="text-[12.5px] text-[var(--bh-clay)]" data-testid={`call-lead-error-${id}`}>{error}</p>
          )}
        </div>
      )}
      {textOpen && (
        <div className="basis-full rounded-md border bh-hairline p-3 space-y-2" data-testid={`text-lead-confirm-${id}`}>
          <p className="text-[12px] text-[var(--bh-ink-3)]">This is the text that will be sent.</p>
          <textarea
            className="w-full min-h-[7rem] rounded-md border bh-hairline bg-transparent p-2 text-[13px] text-[var(--bh-ink)]"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            data-testid={`text-lead-preview-${id}`}
          />
          <div className="flex gap-2">
            <button type="button" className={btn} onClick={sendText} disabled={busy === "text"} data-testid={`text-lead-send-${id}`}>
              Send text
            </button>
            <button type="button" className={btn} onClick={() => setTextOpen(false)}>
              Cancel
            </button>
          </div>
          {error && (
            <p className="text-[12.5px] text-[var(--bh-clay)]" data-testid={`text-lead-error-${id}`}>{error}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default LeadContactActions;
