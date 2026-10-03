import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

// Reasons come from the backend (services/rejection_service.py) so the app,
// the Airtable options and the learning loop share one vocabulary. Cached for
// the session.
let reasonsCache = null;
export const loadReasons = () => {
  if (!reasonsCache) {
    reasonsCache = api.rejectionReasons().catch((e) => {
      reasonsCache = null;
      throw e;
    });
  }
  return reasonsCache;
};

/**
 * passWithUndo — pass on a lead and show an Undo toast. Shared by the sheet
 * and the backlog tagger so both behave the same.
 */
export const passWithUndo = async (opp, reason, note, onChange) => {
  const res = await api.passOpportunity(opp.id, reason.key, note || undefined);
  onChange?.(res);
  const where = res.fell_back ? ` (saved as “${res.rejection_reason_written}”)` : "";
  toast.success(`Passed on ${opp.name || "this lead"} — ${reason.label}${where}`, {
    duration: 8000,
    action: {
      label: "Undo",
      onClick: async () => {
        try {
          await api.undoPass(opp.id, res.previous_status);
          toast("Undone — lead is back where it was.");
          onChange?.(null);
        } catch (e) {
          toast.error(e?.response?.data?.detail || "Couldn't undo — fix it in the record");
        }
      },
    },
  });
  return res;
};

// "Wrong trade (roof, solar…)" under a "Wrong trade" title → "roof, solar…".
const extraDetail = (r) => {
  if (!r.detail || r.detail === r.label) return null;
  if (!r.detail.startsWith(r.label)) return r.detail;
  const rest = r.detail.slice(r.label.length).replace(/^[\s—(-]+/, "").replace(/\)$/, "");
  return rest.length > 5 ? rest : null;
};

export const ReasonGrid = ({ reasons, busyKey, onPick, compact = false }) => (
  <div className="grid grid-cols-2 gap-2" data-testid="reason-grid">
    {reasons.map((r) => (
      <button
        key={r.key}
        type="button"
        disabled={Boolean(busyKey)}
        onClick={() => onPick(r)}
        data-testid={`reason-${r.key}`}
        className="text-left rounded-md border bh-hairline bg-[var(--bh-surface)] hover:bg-[var(--bh-surface-2)] active:scale-[0.99] transition p-3 min-h-[64px] disabled:opacity-60"
      >
        <span className="flex items-center gap-1.5 text-[14px] font-semibold text-[var(--bh-ink)]">
          {busyKey === r.key && <Loader2 size={13} className="animate-spin" />}
          {r.label}
        </span>
        {!compact && extraDetail(r) && (
          <span className="block mt-0.5 text-[11.5px] leading-snug text-[var(--bh-ink-mute)]">{extraDetail(r)}</span>
        )}
      </button>
    ))}
  </div>
);

/**
 * PassSheet — "Why pass?" One tap on a reason disqualifies the lead, saves
 * the Rejection reason and journals it to Activity Log. Nothing is sent.
 */
const PassSheet = ({ opp, open, onOpenChange, onPassed }) => {
  const [reasons, setReasons] = useState([]);
  const [note, setNote] = useState("");
  const [busyKey, setBusyKey] = useState(null);

  useEffect(() => {
    if (!open) return;
    setNote("");
    loadReasons()
      .then(setReasons)
      .catch(() => toast.error("Couldn't load reasons — try again"));
  }, [open]);

  const pick = async (reason) => {
    setBusyKey(reason.key);
    try {
      await passWithUndo(opp, reason, note.trim(), onPassed);
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't save the pass");
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        className="max-h-[90vh] overflow-y-auto p-0 border-t bh-hairline rounded-t-xl sm:max-w-xl sm:mx-auto"
        style={{ background: "var(--bh-bg)" }}
        data-testid="pass-sheet"
      >
        <SheetHeader className="px-5 pt-5 pb-3 text-left space-y-1">
          <div className="mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--bh-ink-mute)]">Pass</div>
          <SheetTitle className="font-display text-[22px] leading-tight text-[var(--bh-ink)]">
            Why not {opp?.name || "this one"}?
          </SheetTitle>
          <SheetDescription className="text-[12.5px] text-[var(--bh-ink-3)]">
            One tap saves it. Every reason teaches the classifier what to stop sending you.
          </SheetDescription>
        </SheetHeader>
        <div className="px-5 pb-6 space-y-3">
          <ReasonGrid reasons={reasons} busyKey={busyKey} onPick={pick} />
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note first (optional) — e.g. “roof only”"
            data-testid="pass-note"
            className="w-full h-11 px-3 rounded-md border bh-hairline bg-[var(--bh-surface)] text-[14px] text-[var(--bh-ink)] placeholder:text-[var(--bh-ink-faint)] focus:outline-none focus:border-[var(--bh-brass)]"
          />
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default PassSheet;
