import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import TopHeader from "@/components/TopHeader";
import DraftNoteDrawer from "@/components/DraftNoteDrawer";
import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/formatters";
import {
  PenLine,
  ExternalLink,
  CheckCircle2,
  Archive,
  Inbox,
  ShieldCheck,
  Filter,
} from "lucide-react";

const STATUS_FILTERS = [
  { key: "Ready for Ryan review", label: "Ready for review" },
  { key: "Approved for manual send", label: "Approved for manual send" },
  { key: "Draft", label: "Drafts in progress" },
  { key: "Archived", label: "Archived" },
];

const StatusBadge = ({ status }) => {
  const map = {
    "Ready for Ryan review": {
      bg: "var(--bh-brass-mute)",
      color: "var(--bh-brass)",
      border: "var(--bh-hair-warm)",
    },
    "Approved for manual send": {
      bg: "var(--bh-olive-mute)",
      color: "var(--bh-olive)",
      border: "rgba(107,122,85,0.32)",
    },
    Draft: {
      bg: "var(--bh-surface-2)",
      color: "var(--bh-ink-3)",
      border: "var(--bh-hair)",
    },
    Archived: {
      bg: "var(--bh-surface-2)",
      color: "var(--bh-ink-mute)",
      border: "var(--bh-hair)",
    },
  };
  const s = map[status] || map.Draft;
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full border font-medium whitespace-nowrap"
      style={{ background: s.bg, color: s.color, borderColor: s.border }}
    >
      {status}
    </span>
  );
};

const PlaybookChip = ({ slug }) => {
  if (!slug) return null;
  const label =
    slug === "builder" ? "Builder / Remodeler"
    : slug === "designer" ? "Interior Designer"
    : slug === "pool_outdoor" ? "Pool / Outdoor Living"
    : slug === "blank" ? "Custom"
    : slug;
  return (
    <span
      className="text-[10.5px] px-2 py-0.5 rounded border bh-hairline whitespace-nowrap"
      style={{ color: "var(--bh-ink-3)" }}
    >
      {label}
    </span>
  );
};

const DraftRow = ({ draft, onOpen, onAdvance, onArchive, busy }) => {
  const preview = (draft.body || "")
    .replace(/^\s*(subject:.*|hi|hey|hello).*/i, "")
    .trim()
    .slice(0, 220);
  return (
    <div
      data-testid={`queue-row-${draft.draft_id}`}
      className="bh-surface rounded-md p-4 sm:p-5 flex flex-col sm:flex-row sm:items-start gap-4"
    >
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            to={`/opportunities/${draft.opportunity_id}`}
            data-testid={`queue-open-opp-${draft.draft_id}`}
            className="font-display font-semibold text-[15px] text-[var(--bh-ink)] hover:text-[var(--bh-brass)] truncate"
          >
            {draft.opportunity_name || draft.opportunity_id}
          </Link>
          <StatusBadge status={draft.review_status} />
          <PlaybookChip slug={draft.selected_playbook} />
          <span className="text-[11px] text-[var(--bh-ink-3)]">
            · updated {fmtRelative(draft.updated_at)}
          </span>
        </div>
        {draft.subject && (
          <div
            className="text-[13.5px] font-medium truncate"
            style={{ color: "var(--bh-ink-2)" }}
            data-testid={`queue-subject-${draft.draft_id}`}
          >
            {draft.subject}
          </div>
        )}
        {preview && (
          <div className="text-[12.5px] leading-relaxed text-[var(--bh-ink-3)] line-clamp-2">
            {preview}
          </div>
        )}
        {draft.internal_note && (
          <div
            className="text-[11.5px] leading-relaxed rounded px-2 py-1.5 inline-block max-w-full"
            style={{
              background: "var(--bh-surface-2)",
              color: "var(--bh-ink-3)",
              border: "1px solid var(--bh-hair)",
            }}
          >
            Note · {draft.internal_note}
          </div>
        )}
      </div>
      <div className="flex flex-wrap sm:flex-col gap-1.5 shrink-0 sm:w-[210px]">
        <button
          type="button"
          onClick={() => onOpen(draft)}
          data-testid={`queue-review-${draft.draft_id}`}
          className="text-[12.5px] h-9 px-3 rounded-md border font-medium inline-flex items-center justify-center gap-1.5"
          style={{
            background: "var(--bh-brass-mute)",
            borderColor: "var(--bh-hair-warm)",
            color: "var(--bh-brass)",
          }}
        >
          <PenLine size={13} /> Review draft
        </button>
        {draft.review_status === "Ready for Ryan review" && (
          <button
            type="button"
            onClick={() => onAdvance(draft, "Approved for manual send")}
            disabled={busy === draft.draft_id}
            data-testid={`queue-approve-${draft.draft_id}`}
            className="text-[12.5px] h-9 px-3 rounded-md border inline-flex items-center justify-center gap-1.5"
            style={{
              background: "var(--bh-olive-mute)",
              borderColor: "rgba(107,122,85,0.32)",
              color: "var(--bh-olive)",
            }}
          >
            <CheckCircle2 size={13} /> Mark approved
          </button>
        )}
        {draft.review_status === "Approved for manual send" && (
          <button
            type="button"
            onClick={() => onAdvance(draft, "Ready for Ryan review")}
            disabled={busy === draft.draft_id}
            data-testid={`queue-unapprove-${draft.draft_id}`}
            className="text-[12.5px] h-9 px-3 rounded-md border bh-hairline inline-flex items-center justify-center gap-1.5"
            style={{ color: "var(--bh-ink-3)" }}
          >
            Move back to review
          </button>
        )}
        {draft.review_status !== "Archived" && (
          <button
            type="button"
            onClick={() => onArchive(draft)}
            disabled={busy === draft.draft_id}
            data-testid={`queue-archive-${draft.draft_id}`}
            className="text-[12.5px] h-9 px-3 rounded-md border bh-hairline inline-flex items-center justify-center gap-1.5"
            style={{ color: "var(--bh-ink-3)" }}
          >
            <Archive size={13} /> Archive
          </button>
        )}
        <Link
          to={`/opportunities/${draft.opportunity_id}`}
          data-testid={`queue-open-detail-${draft.draft_id}`}
          className="text-[11.5px] text-[var(--bh-ink-3)] hover:text-[var(--bh-brass)] inline-flex items-center justify-center gap-1 pt-1"
        >
          <ExternalLink size={11} /> Open opportunity
        </Link>
      </div>
    </div>
  );
};

const ReviewQueue = () => {
  const [status, setStatus] = useState("Ready for Ryan review");
  const [state, setState] = useState({ loading: true, drafts: [], counts: {} });
  const [busy, setBusy] = useState(null);
  const [openOpp, setOpenOpp] = useState(null);

  const load = useCallback(async (nextStatus = status) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const data = await api.listDraftQueue(nextStatus);
      setState({
        loading: false,
        drafts: data.drafts || [],
        counts: data.counts || {},
      });
    } catch {
      setState({ loading: false, drafts: [], counts: {} });
      toast.error("Could not load review queue");
    }
  }, [status]);

  useEffect(() => {
    load(status);
  }, [status, load]);

  const changeStatus = (s) => setStatus(s);

  const handleOpen = useCallback(async (draft) => {
    try {
      const opp = await api.getOpportunity(draft.opportunity_id);
      setOpenOpp(opp);
    } catch {
      toast.error("Could not load opportunity");
    }
  }, []);

  const handleAdvance = useCallback(async (draft, nextStatus) => {
    setBusy(draft.draft_id);
    try {
      await api.updateDraft(draft.draft_id, { review_status: nextStatus });
      toast.success(`Moved to "${nextStatus}"`);
      load(status);
    } catch {
      toast.error("Update failed");
    } finally {
      setBusy(null);
    }
  }, [load, status]);

  const handleArchive = useCallback(async (draft) => {
    setBusy(draft.draft_id);
    try {
      await api.updateDraft(draft.draft_id, { review_status: "Archived" });
      toast.success("Draft archived");
      load(status);
    } catch {
      toast.error("Archive failed");
    } finally {
      setBusy(null);
    }
  }, [load, status]);

  const readyCount = state.counts["Ready for Ryan review"] || 0;
  const approvedCount = state.counts["Approved for manual send"] || 0;

  const heroSubtitle = useMemo(() => {
    if (state.loading) return "Loading";
    const total = readyCount + approvedCount;
    if (!total) return "Nothing waiting for Ryan right now";
    return `${readyCount} ready for review · ${approvedCount} approved for manual send`;
  }, [state.loading, readyCount, approvedCount]);

  return (
    <>
      <TopHeader pageTitle="Review Queue" subtitle={heroSubtitle} />
      <div className="px-4 lg:px-8 py-6 space-y-5">
        {/* Hero */}
        <section
          data-testid="queue-hero"
          className="bh-surface rounded p-5 sm:p-6"
          style={{ borderTop: "2px solid var(--bh-brass)" }}
        >
          <div className="flex items-center gap-2">
            <Inbox size={13} style={{ color: "var(--bh-brass)" }} strokeWidth={1.75} />
            <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
              Ready for Ryan review
            </span>
            <span
              className="text-[11px] px-2 py-0.5 rounded-full ml-2 inline-flex items-center gap-1"
              style={{
                background: "var(--bh-surface-2)",
                border: "1px solid var(--bh-hair)",
                color: "var(--bh-ink-3)",
              }}
            >
              <ShieldCheck size={10} strokeWidth={1.75} /> Draft-only · nothing sends from this screen
            </span>
          </div>
          <h2 className="mt-3 font-display text-[26px] sm:text-[32px] text-[var(--bh-ink)] tracking-tight max-w-2xl">
            Every draft you flagged for review, in one place.
          </h2>
          <p className="mt-2 text-[14px] text-[var(--bh-ink-3)] max-w-2xl leading-relaxed">
            When a partner draft is marked "Ready for Ryan review" it lands
            here. Open the drawer to read the finished message, mark it
            Approved for manual send, or archive it if it's no longer useful.
            Approving is a decision — it never triggers a send.
          </p>
        </section>

        {/* Status filter */}
        <section className="flex flex-wrap items-center gap-1.5" data-testid="queue-filters">
          <span className="bh-eyebrow inline-flex items-center gap-1 mr-1">
            <Filter size={11} /> Status
          </span>
          {STATUS_FILTERS.map((f) => {
            const n = state.counts[f.key] || 0;
            const active = status === f.key;
            return (
              <button
                key={f.key}
                type="button"
                data-testid={`queue-filter-${f.key.toLowerCase().replace(/\s+/g, "-")}`}
                onClick={() => changeStatus(f.key)}
                className="text-[12px] px-2.5 py-1 rounded-full border transition-colors duration-150"
                style={
                  active
                    ? {
                        background: "var(--bh-brass-mute)",
                        borderColor: "var(--bh-hair-warm)",
                        color: "var(--bh-brass)",
                      }
                    : {
                        background: "var(--bh-surface)",
                        borderColor: "var(--bh-hair)",
                        color: "var(--bh-ink-3)",
                      }
                }
              >
                {f.label}
                <span
                  className="ml-1.5 tabular-nums"
                  style={{ color: active ? "var(--bh-brass)" : "var(--bh-ink-mute)" }}
                >
                  {n}
                </span>
              </button>
            );
          })}
        </section>

        {/* List */}
        {state.loading ? (
          <div className="bh-surface rounded p-12 text-center text-[var(--bh-ink-3)] text-sm">
            Loading drafts…
          </div>
        ) : state.drafts.length === 0 ? (
          <div
            data-testid="queue-empty"
            className="bh-surface rounded p-10 space-y-3 text-center"
          >
            <div className="inline-flex items-center gap-2 text-[var(--bh-ink)]">
              <Inbox size={16} style={{ color: "var(--bh-olive)" }} />
              <span className="font-display text-lg font-semibold">
                Nothing in "{STATUS_FILTERS.find((s) => s.key === status)?.label || status}" yet.
              </span>
            </div>
            <p className="text-[13px] text-[var(--bh-ink-3)] max-w-lg mx-auto leading-relaxed">
              Open any Partner Pipeline opportunity, click{" "}
              <span className="font-medium text-[var(--bh-ink-2)]">Draft a Note</span>,
              write it up, and set the status to{" "}
              <span className="font-medium text-[var(--bh-ink-2)]">Ready for Ryan review</span>.
              It will show up here.
            </p>
          </div>
        ) : (
          <div className="space-y-2" data-testid="queue-list">
            {state.drafts.map((d) => (
              <DraftRow
                key={d.draft_id}
                draft={d}
                busy={busy}
                onOpen={handleOpen}
                onAdvance={handleAdvance}
                onArchive={handleArchive}
              />
            ))}
          </div>
        )}
      </div>

      <DraftNoteDrawer
        open={!!openOpp}
        onOpenChange={(o) => {
          if (!o) {
            setOpenOpp(null);
            load(status);
          }
        }}
        opportunity={openOpp}
      />
    </>
  );
};

export default ReviewQueue;
