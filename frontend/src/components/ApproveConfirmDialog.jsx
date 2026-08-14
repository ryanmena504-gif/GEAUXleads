import React, { useEffect, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AlertTriangle, CheckCircle2, Loader2, Mail, Phone, User } from "lucide-react";

const Row = ({ icon: Icon, label, value, missing }) => (
  <div className="flex items-start gap-2.5">
    <Icon
      size={13}
      className={missing ? "text-neutral-600 mt-0.5" : "text-amber-400 mt-0.5"}
    />
    <div className="min-w-0">
      <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
        {label}
      </div>
      <div
        className={
          "text-sm truncate " + (missing ? "text-neutral-500 italic" : "text-neutral-100")
        }
      >
        {value || "Not available"}
      </div>
    </div>
  </div>
);

/**
 * Restates who is about to be contacted and what is unverified, then requires a
 * separate deliberate confirmation. The checkbox exists so acknowledging a
 * warning is a distinct act from clicking Approve — the acknowledged codes are
 * sent to the server and recorded on the audit event.
 */
export const ApproveConfirmDialog = ({
  open,
  onOpenChange,
  lead,
  eligibility,
  busy,
  onConfirm,
}) => {
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (open) setAcknowledged(false);
  }, [open]);

  if (!lead) return null;

  const recipient = eligibility?.recipient || {};
  const warnings = eligibility?.warnings || [];
  const needsAck = warnings.length > 0;
  const canConfirm = !busy && (!needsAck || acknowledged);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        data-testid="approve-confirm-dialog"
        className="bh-surface border-white/10 text-neutral-100"
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="font-display">
            Approve outreach for {lead.name || "this lead"}?
          </AlertDialogTitle>
          <AlertDialogDescription className="text-neutral-400">
            This records your approval on the Airtable record. No message is sent
            — dispatch is not connected yet.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3 rounded border bh-hairline p-3">
          <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
            Who this is about
          </div>
          <Row
            icon={User}
            label="Contact"
            value={recipient.counterparty}
            missing={!recipient.counterparty}
          />
          <Row
            icon={Phone}
            label="Phone"
            value={recipient.phone}
            missing={!recipient.phone}
          />
          <Row
            icon={Mail}
            label="Email"
            value={recipient.email}
            missing={!recipient.email}
          />
          <Row
            icon={CheckCircle2}
            label="Address"
            value={recipient.address}
            missing={!recipient.address}
          />
        </div>

        {needsAck && (
          <div
            className="rounded border border-amber-500/30 bg-amber-500/[0.06] p-3 space-y-2"
            data-testid="approve-warnings"
          >
            <div className="mono text-[9px] uppercase tracking-widest text-amber-300 inline-flex items-center gap-1.5">
              <AlertTriangle size={11} /> {warnings.length} unresolved warning
              {warnings.length === 1 ? "" : "s"}
            </div>
            <ul className="space-y-1.5">
              {warnings.map((w) => (
                <li key={w.code} className="text-xs text-neutral-300 leading-relaxed">
                  <span className="text-amber-200">{w.message}</span>
                  {w.remediation && (
                    <span className="text-neutral-500"> — {w.remediation}</span>
                  )}
                </li>
              ))}
            </ul>
            <label className="flex items-start gap-2 pt-1 cursor-pointer">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                data-testid="approve-acknowledge"
                className="mt-0.5 accent-amber-500"
              />
              <span className="text-xs text-neutral-300">
                I have read these warnings and want to approve anyway.
              </span>
            </label>
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel
            data-testid="approve-cancel"
            className="bg-transparent border-white/10 text-neutral-300 hover:bg-white/[0.03] hover:text-neutral-100"
          >
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            data-testid="approve-confirm"
            disabled={!canConfirm}
            onClick={(e) => {
              // Keep the dialog mounted while the request is in flight so a
              // 409 can be surfaced in place rather than behind a closed modal.
              e.preventDefault();
              onConfirm(warnings.map((w) => w.code));
            }}
            className="bg-amber-500 text-neutral-950 hover:bg-amber-400 disabled:opacity-50"
          >
            {busy ? (
              <Loader2 size={14} className="animate-spin mr-1.5" />
            ) : (
              <CheckCircle2 size={14} className="mr-1.5" />
            )}
            Confirm approval
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default ApproveConfirmDialog;
