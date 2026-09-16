import React, { useMemo, useState } from "react";
import { Download, Mail, Archive, ArchiveRestore, X } from "lucide-react";
import { toast } from "sonner";

// URI-length guard for the mailto BCC handoff — Safari caps around 2000
// chars; use 1800 for safety so subject + trailing bits still fit.
const MAILTO_URL_LIMIT = 1800;

/**
 * Bulk-action bar. Only renders when >=1 record is selected.
 * All actions respect founding rules (never sends, never mutates Airtable).
 */
export const BulkActionBar = ({
  selected,           // Set of record IDs
  records,            // full list currently in view (for lookups)
  onClear,
  onExportCsv,        // (ids) => triggers CSV download (nullable)
  onArchive,          // (ids) => Promise (nullable)
  onUnarchive,        // (ids) => Promise (nullable, present when showArchived)
  archivedMode = false,
  testId = "bulk-bar",
}) => {
  const [busy, setBusy] = useState(false);
  const ids = useMemo(() => Array.from(selected || []), [selected]);
  if (ids.length === 0) return null;

  const byId = new Map(records.map((r) => [r.id, r]));
  const withEmail = ids.map((id) => byId.get(id)).filter((r) => r && (r.email || r.email_alt));
  const emails = withEmail.map((r) => (r.email || r.email_alt).trim());
  const skipped = ids.length - withEmail.length;

  const openMailto = () => {
    if (emails.length === 0) {
      toast.error("No selected records have an email on file.");
      return;
    }
    const bcc = emails.join(",");
    const single = `mailto:?bcc=${encodeURIComponent(bcc)}`;
    if (single.length <= MAILTO_URL_LIMIT) {
      if (skipped > 0)
        toast.message(`${skipped} record(s) skipped — no email on file.`);
      window.location.href = single;
      return;
    }
    const tabCount = withEmail.length;
    const proceed = window.confirm(
      `URL too long for a single BCC handoff. Bloodhound will open ${tabCount} native mail drafts (one per address). Continue?`,
    );
    if (!proceed) return;
    withEmail.forEach((r) =>
      window.open(`mailto:${encodeURIComponent((r.email || r.email_alt).trim())}`, "_blank"),
    );
  };

  const runArchive = async () => {
    if (!onArchive) return;
    setBusy(true);
    try {
      await onArchive(ids);
      toast.success(
        `${ids.length} hidden in Bloodhound. Airtable and Make are unchanged.`,
      );
      onClear && onClear();
    } catch (e) {
      toast.error(e?.message || "Archive failed");
    } finally { setBusy(false); }
  };
  const runUnarchive = async () => {
    if (!onUnarchive) return;
    setBusy(true);
    try {
      await onUnarchive(ids);
      toast.success(`${ids.length} unhidden.`);
      onClear && onClear();
    } catch (e) {
      toast.error(e?.message || "Unarchive failed");
    } finally { setBusy(false); }
  };

  return (
    <div
      data-testid={testId}
      className="sticky top-14 z-20 flex items-center gap-2 flex-wrap p-2 rounded-md border bh-hairline"
      style={{ background: "var(--bh-surface)" }}
    >
      <span
        data-testid={`${testId}-count`}
        className="mono uppercase tracking-widest text-[10px] text-[var(--bh-ink-mute)] px-2"
      >
        {ids.length} selected
      </span>
      {onExportCsv && (
        <button
          type="button"
          onClick={() => onExportCsv(ids)}
          data-testid={`${testId}-export`}
          className="inline-flex items-center gap-1.5 h-11 px-3 rounded-md text-[12.5px] font-semibold border bh-hairline text-[var(--bh-ink-2)] hover:text-[var(--bh-ink)]"
        >
          <Download size={12} strokeWidth={2} /> Export CSV
        </button>
      )}
      <button
        type="button"
        onClick={openMailto}
        data-testid={`${testId}-mailto`}
        className="inline-flex items-center gap-1.5 h-11 px-3 rounded-md text-[12.5px] font-semibold border"
        style={{
          background: "var(--bh-brass)",
          color: "var(--bh-surface)",
          borderColor: "var(--bh-brass)",
        }}
      >
        <Mail size={12} strokeWidth={2} /> Draft {withEmail.length} email{withEmail.length === 1 ? "" : "s"}
      </button>
      {!archivedMode && onArchive && (
        <button
          type="button"
          onClick={runArchive}
          disabled={busy}
          data-testid={`${testId}-archive`}
          title="Hides in Bloodhound only — Airtable and Make records are not touched. Reversible from the Show archived toggle."
          className="inline-flex items-center gap-1.5 h-11 px-3 rounded-md text-[12.5px] font-semibold border bh-hairline text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
        >
          <Archive size={12} strokeWidth={2} /> Hide (Bloodhound only)
        </button>
      )}
      {archivedMode && onUnarchive && (
        <button
          type="button"
          onClick={runUnarchive}
          disabled={busy}
          data-testid={`${testId}-unarchive`}
          className="inline-flex items-center gap-1.5 h-11 px-3 rounded-md text-[12.5px] font-semibold border bh-hairline text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
        >
          <ArchiveRestore size={12} strokeWidth={2} /> Unhide
        </button>
      )}
      <button
        type="button"
        onClick={onClear}
        data-testid={`${testId}-clear`}
        className="ml-auto inline-flex items-center gap-1 h-11 px-2 text-[11px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]"
      >
        <X size={11} /> Clear
      </button>
    </div>
  );
};

export default BulkActionBar;
