import React, { useCallback, useEffect, useState } from "react";
import { Radio, Phone, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

/**
 * TwilioIntel — read-only carrier / line-type / caller-name pill card.
 *
 * Feature-flagged: on first render we probe `/api/lookup/twilio/status`.
 * If Twilio isn't configured (missing SID/token) the card never renders —
 * the Lookup page keeps working exactly like it did before, no error
 * banner, no broken button.
 *
 * Auto-runs on mount for the phone number in the URL. Includes a
 * "Retry" button on failure so a Twilio 429 doesn't make Ryan reload
 * the whole page.
 */
const LINE_TYPE_LABEL = {
  mobile: "Mobile",
  landline: "Landline",
  fixedVoip: "VoIP (fixed)",
  nonFixedVoip: "VoIP (non-fixed)",
  personal: "Personal",
  tollFree: "Toll-free",
  premium: "Premium rate",
  sharedCost: "Shared cost",
  uan: "UAN",
  voicemail: "Voicemail",
  pager: "Pager",
  unknown: "Unknown",
};

const line = (t) => LINE_TYPE_LABEL[t] || t || "Unknown";

// Rough spam-shape heuristic for iOS callers — non-fixed VoIP + no CNAM
// almost always means burner / spam trunk. We surface it as a WARN chip
// so Ryan sees at a glance without needing Twilio's SMS-pumping paid tier.
const spamShape = (data) => {
  const t = (data.line_type || "").toLowerCase();
  if (t === "nonfixedvoip" && !data.caller_name) return "Likely burner / spam";
  return null;
};

export const TwilioIntel = ({ phoneNumber, testId = "twilio-intel" }) => {
  const [enabled, setEnabled] = useState(null); // null=probing, true, false
  const [state, setState] = useState({ status: "idle", data: null, error: null });

  useEffect(() => {
    let mounted = true;
    api
      .twilioLookupStatus()
      .then((r) => mounted && setEnabled(!!r?.enabled))
      .catch(() => mounted && setEnabled(false));
    return () => {
      mounted = false;
    };
  }, []);

  const run = useCallback(async () => {
    if (!phoneNumber) return;
    setState({ status: "loading", data: null, error: null });
    try {
      const data = await api.twilioLookup(phoneNumber);
      setState({ status: "ok", data, error: null });
    } catch (err) {
      const status = err?.response?.status;
      const detail =
        err?.response?.data?.detail || err?.message || "Twilio Lookup failed";
      setState({ status: "error", data: null, error: { status, detail } });
    }
  }, [phoneNumber]);

  useEffect(() => {
    if (enabled === true && phoneNumber) run();
  }, [enabled, phoneNumber, run]);

  if (enabled === null || enabled === false) return null;

  const { data } = state;
  const spam = data ? spamShape(data) : null;

  return (
    <div
      data-testid={testId}
      className="rounded-md border bh-hairline p-3 space-y-2"
      style={{ background: "var(--bh-surface-2)" }}
    >
      <div className="flex items-center gap-1.5">
        <Radio size={12} className="text-[var(--bh-brass)]" />
        <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
          Number intel
        </span>
        <span className="ml-auto text-[10px] mono uppercase tracking-widest text-[var(--bh-ink-mute)]">
          via Twilio
        </span>
      </div>

      {state.status === "loading" && (
        <div className="flex items-center gap-2 text-[12.5px] text-[var(--bh-ink-2)] py-1">
          <Loader2 size={12} className="animate-spin text-[var(--bh-brass)]" />
          Looking up carrier + line type…
        </div>
      )}

      {state.status === "error" && (
        <div
          className="flex items-start gap-2 rounded-md border p-2.5 text-[12px]"
          style={{
            borderColor: "rgba(138,90,69,0.28)",
            background: "rgba(138,90,69,0.08)",
            color: "#a67055",
          }}
        >
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <div className="flex-1">
            <div>{state.error?.detail}</div>
            {state.error?.status && (
              <div className="mono text-[10px] uppercase tracking-widest mt-0.5 opacity-70">
                HTTP {state.error.status}
              </div>
            )}
            <button
              type="button"
              onClick={run}
              className="mt-2 text-[11px] font-medium underline hover:no-underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {state.status === "ok" && data && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {data.line_type && (
              <span
                data-testid={`${testId}-line-type`}
                className="inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[10.5px] font-semibold tabular-nums"
                style={{ color: "var(--bh-ink-2)", background: "var(--bh-surface)" }}
              >
                <Phone size={9} strokeWidth={2} /> {line(data.line_type)}
              </span>
            )}
            {data.carrier_name && (
              <span
                data-testid={`${testId}-carrier`}
                className="inline-flex items-center rounded-full px-2 py-[2px] text-[10.5px] tabular-nums"
                style={{ color: "var(--bh-ink-3)", background: "var(--bh-surface)" }}
              >
                {data.carrier_name}
              </span>
            )}
            {data.country_code && data.country_code !== "US" && (
              <span
                className="inline-flex items-center rounded-full px-2 py-[2px] text-[10.5px] tabular-nums"
                style={{ color: "var(--bh-ink-3)", background: "var(--bh-surface)" }}
              >
                {data.country_code}
              </span>
            )}
            {spam && (
              <span
                data-testid={`${testId}-spam`}
                className="inline-flex items-center rounded-full px-2 py-[2px] text-[10.5px] font-semibold"
                style={{ color: "#8a5a45", background: "rgba(138,90,69,0.14)" }}
              >
                ⚠ {spam}
              </span>
            )}
          </div>
          {data.caller_name && (
            <div
              data-testid={`${testId}-caller-name`}
              className="text-[13px] text-[var(--bh-ink)]"
            >
              <span className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)] mr-2">
                CNAM
              </span>
              {data.caller_name}
              {data.caller_type && (
                <span className="ml-1 text-[var(--bh-ink-3)]">({data.caller_type})</span>
              )}
            </div>
          )}
          {!data.caller_name && !data.carrier_name && (
            <div className="text-[11.5px] text-[var(--bh-ink-3)]">
              Twilio has no carrier or CNAM record for this number.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TwilioIntel;
