import React, { useCallback, useEffect, useRef, useState } from "react";
import { PenLine, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * OutreachWriterButton — on-demand outreach writer trigger (Make webhook).
 *
 * Fires the Make scenario that writes the personalized first message for this
 * one record — no backlog, no fees unless tapped. The scenario runs async and
 * writes the message back to Airtable; the backend returns 202 immediately.
 *
 * Renders in the Actions panel next to the Email Now button. When a first
 * message already exists on the record, the label becomes "Re-write outreach".
 * If OUTREACH_WRITER_WEBHOOK is not configured, the backend 503s and the
 * button shows the error inline — never a crash.
 */
export const OutreachWriterButton = ({ opp }) => {
  const [state, setState] = useState({ status: "idle", error: null, elapsed: 0 });
  const timerRef = useRef(null);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => stopTimer, [stopTimer]);

  const run = useCallback(async () => {
    setState({ status: "running", error: null, elapsed: 0 });
    try {
      const res = await api.outreachWrite(opp.id);
      toast.success(res?.message || "Outreach writer running — writing your first message.");
    } catch (err) {
      const detail =
        err?.response?.data?.detail || err?.message || "Outreach writer failed to start";
      setState({ status: "error", error: detail, elapsed: 0 });
      toast.error(detail);
      return;
    }
    timerRef.current = setInterval(() => {
      setState((s) => {
        const elapsed = s.elapsed + 1;
        if (elapsed >= 40) {
          stopTimer();
          return { ...s, status: "done", elapsed };
        }
        return { ...s, elapsed };
      });
    }, 1000);
  }, [opp.id, stopTimer]);

  const hasMessage = Boolean(opp.first_message || opp.first_contact_message);

  if (state.status === "running") {
    return (
      <div className="flex items-center gap-2 text-[12.5px] text-[var(--bh-ink-2)] py-1.5">
        <Loader2 size={13} className="animate-spin text-[var(--bh-brass)]" />
        Writing… {state.elapsed}s
      </div>
    );
  }

  if (state.status === "done") {
    return (
      <div className="space-y-1.5">
        <div className="text-[12.5px] text-[var(--bh-ink-2)]">
          Message written — refresh the page to see it.
        </div>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="text-[11px] font-medium underline hover:no-underline text-[var(--bh-ink-2)]"
        >
          Refresh now
        </button>
      </div>
    );
  }

  if (state.status === "error") {
    return (
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
          <div>{state.error}</div>
          <button
            type="button"
            onClick={() => setState({ status: "idle", error: null, elapsed: 0 })}
            className="mt-2 text-[11px] font-medium underline hover:no-underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={run}
      data-testid="write-outreach-btn"
      title="Write the first outreach message for this lead — on-demand, one record."
      className="w-full flex items-center gap-2 px-3 h-9 rounded text-sm border bh-hairline text-[var(--bh-ink-2)] hover:bg-[var(--bh-surface-2)] transition-colors duration-150"
    >
      <PenLine size={14} />
      {hasMessage ? "Re-write outreach" : "Write outreach"}
    </button>
  );
};

export default OutreachWriterButton;
