import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import LaneBadge from "@/components/LaneBadge";
import { Copy, Save, Trash2, ShieldCheck, PenLine, Lock } from "lucide-react";
import { api } from "@/lib/api";
import OpenInMessages from "@/components/OpenInMessages";

/**
 * DraftNoteDrawer — partner-outreach preparation ONLY.
 *
 * Ground rules baked into this component (do not remove):
 *   - Never contains a Send / Schedule / Launch button.
 *   - Never calls a mail, SMS, DM, or webhook API.
 *   - Copy-to-clipboard is allowed. Save to server-side draft store is allowed.
 *   - Always shows the persistent guardrail label.
 *   - Never uses permit data or property address as a reason to contact a homeowner.
 */

const REVIEW_STATUSES = [
  "Draft",
  "Ready for Ryan review",
  "Approved for manual send",
  "Archived",
];

const REVIEW_STATUS_LABEL = {
  Draft: "Still writing",
  "Ready for Ryan review": "Needs a look",
  "Approved for manual send": "Ready to contact",
  Archived: "Archived",
};

// Map an opportunity's project_type + name/why to a playbook audience slug.
// Falls back to `null` (which triggers "start from blank" behavior).
const audienceFromOpportunity = (opp) => {
  if (!opp) return null;
  const hay = [
    opp.project_type,
    opp.opportunity_type,
    opp.name,
    opp.company,
    opp.recommendation_reason,
    opp.evidence_summary,
    opp.why_lead_matters,
    opp.source,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (!hay) return null;
  // Pool/outdoor takes precedence — names like "Backyard Living" or
  // "Pool Pros" should route to the Pool / Outdoor Living playbook even if
  // their project_type is a generic "Contractor".
  if (/(pool|outdoor|landscape|hardscape|backyard|deck|patio|spa|hot tub)/.test(hay)) {
    return "pool_outdoor";
  }
  if (/(designer|architect|interior)/.test(hay)) return "designer";
  if (/(contractor|remodel|home builder|builder|construction)/.test(hay)) return "builder";
  return null;
};

const firstName = (fullName) => {
  if (!fullName) return null;
  const s = String(fullName).trim();
  return s ? s.split(/\s+/)[0] : null;
};

// Personalise a raw playbook body using SAFE tokens only. Missing values
// gracefully fall back to neutral phrasing so we never invent a person,
// project, or referral.
const personalise = (raw, tokens) => {
  if (!raw) return "";
  const t = {
    first_name: tokens.contact_first || "team",
    contact_name: tokens.contact_first || "team",
    company_name: tokens.company || "your team",
    market: tokens.service_region || "the area",
    service_region: tokens.service_region || "the area",
    opportunity_type: tokens.opportunity_type || "the work",
    why_fit: tokens.why_fit || "",
    relevant_project_detail: tokens.why_fit || "",
  };
  return raw.replace(/\{\{\s*([a-z_]+)\s*\}\}/gi, (_, k) => t[k] ?? `{{${k}}}`);
};

const BLANK_TEMPLATE = {
  id: "__blank__",
  playbook_id: "blank",
  name: "Start from blank",
  audience_type: "Custom",
  audience_slug: "blank",
  channel: "Email",
  default_subject: "",
  default_draft: "",
  editable_variables: "",
  voice_rules: "",
  approval_note:
    "Draft only. Any outreach must go through Ryan's explicit campaign approval before sending.",
};

const GuardrailBanner = () => (
  <div
    className="flex items-start gap-2 rounded-md border px-3 py-2 text-[12.5px] leading-relaxed"
    style={{
      background: "var(--bh-brass-mute)",
      borderColor: "var(--bh-hair-warm)",
      color: "var(--bh-ink-2)",
    }}
    data-testid="draft-guardrail"
  >
    <Lock size={13} className="mt-0.5 shrink-0" style={{ color: "var(--bh-brass)" }} />
    <span>
      <strong className="font-medium">Draft only.</strong> Nothing sends from
      here. When you&rsquo;re ready, tap Contact them — you press Send on
      your phone.
    </span>
  </div>
);

const Field = ({ label, hint, children }) => (
  <div className="space-y-1.5">
    <div className="flex items-baseline justify-between">
      <span className="bh-eyebrow">{label}</span>
      {hint ? (
        <span className="text-[11px] text-[var(--bh-ink-3)]">{hint}</span>
      ) : null}
    </div>
    {children}
  </div>
);

export const DraftNoteDrawer = ({ open, onOpenChange, opportunity }) => {
  const [playbooks, setPlaybooks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [internalNote, setInternalNote] = useState("");
  const [reviewStatus, setReviewStatus] = useState("Draft");
  const [existingDraftId, setExistingDraftId] = useState(null);
  const [savedDrafts, setSavedDrafts] = useState([]);
  const [saving, setSaving] = useState(false);

  const opp = useMemo(() => opportunity || {}, [opportunity]);
  const tokens = useMemo(() => {
    const contactRaw = opp.decision_maker || opp.contact_name || "";
    return {
      company: opp.company || opp.name || "",
      contact_first: firstName(contactRaw),
      service_region: opp.city || opp.service_region || "",
      opportunity_type: opp.project_type || opp.opportunity_type || "",
      why_fit:
        opp.recommendation_reason ||
        opp.why_lead_matters ||
        opp.evidence_summary ||
        opp.ai_summary ||
        "",
    };
  }, [opp]);

  const options = useMemo(() => [...playbooks, BLANK_TEMPLATE], [playbooks]);
  const selected = options.find((p) => p.id === selectedId) || null;

  // Load playbooks + existing drafts each time the drawer opens for a lead
  useEffect(() => {
    if (!open || !opp.id) return;
    let cancelled = false;
    (async () => {
      try {
        const [pb, drafts] = await Promise.all([
          api.listPlaybooks(),
          api.listDrafts(opp.id),
        ]);
        if (cancelled) return;
        const list = pb?.playbooks || [];
        setPlaybooks(list);
        setSavedDrafts(drafts?.drafts || []);
        // Pick default: latest existing draft, else auto-selected playbook
        const latest = (drafts?.drafts || [])[0];
        if (latest) {
          const match = [...list, BLANK_TEMPLATE].find(
            (p) =>
              p.id === latest.selected_playbook ||
              p.playbook_id === latest.selected_playbook,
          );
          setSelectedId(match ? match.id : BLANK_TEMPLATE.id);
          setSubject(latest.subject || "");
          setBody(latest.body || "");
          setInternalNote(latest.internal_note || "");
          setReviewStatus(latest.review_status || "Draft");
          setExistingDraftId(latest.draft_id);
        } else {
          const wanted = audienceFromOpportunity(opp);
          const auto = list.find((p) => p.audience_slug === wanted) || list[0] || BLANK_TEMPLATE;
          setSelectedId(auto.id);
          setSubject(personalise(auto.default_subject || "", tokens));
          setBody(personalise(auto.default_draft || "", tokens));
          setInternalNote("");
          setReviewStatus("Draft");
          setExistingDraftId(null);
        }
      } catch (err) {
        // Log the real error so future debugging is easy — the drawer stays
        // usable even if the network call failed.
         
        console.error("DraftNoteDrawer load failed", err);
        toast.error("Could not load playbooks");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, opp.id]);

  const switchPlaybook = useCallback(
    (id) => {
      const next = options.find((p) => p.id === id);
      if (!next) return;
      setSelectedId(id);
      setSubject(personalise(next.default_subject || "", tokens));
      setBody(personalise(next.default_draft || "", tokens));
    },
    [options, tokens],
  );

  const copyToClipboard = async () => {
    const payload = `Subject: ${subject}\n\n${body}`.trim();
    try {
      await navigator.clipboard.writeText(payload);
      toast.success("Draft copied to clipboard");
    } catch {
      // Fallback for insecure contexts
      const ta = document.createElement("textarea");
      ta.value = payload;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        toast.success("Draft copied to clipboard");
      } catch {
        toast.error("Copy failed — select and copy manually");
      }
      document.body.removeChild(ta);
    }
  };

  const saveDraft = async () => {
    if (!opp.id) return;
    setSaving(true);
    try {
      const payload = {
        opportunity_id: opp.id,
        opportunity_name: opp.name || opp.company || null,
        selected_playbook: selected?.playbook_id || selected?.id || null,
        subject,
        body,
        internal_note: internalNote,
        review_status: reviewStatus,
      };
      let saved;
      if (existingDraftId) {
        saved = await api.updateDraft(existingDraftId, {
          subject,
          body,
          internal_note: internalNote,
          selected_playbook: payload.selected_playbook,
          review_status: reviewStatus,
        });
      } else {
        saved = await api.createDraft(payload);
        setExistingDraftId(saved.draft_id);
      }
      toast.success("Draft saved");
      // Refresh listing
      const drafts = await api.listDrafts(opp.id);
      setSavedDrafts(drafts?.drafts || []);
      return saved;
    } catch {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const discardChanges = () => {
    onOpenChange(false);
  };

  if (!opp || !opp.id) return null;

  const hasContactName = !!tokens.contact_first;
  const projectTypeLabel = opp.project_type || "Partner";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[560px] p-0 border-l bh-hairline"
        style={{ background: "var(--bh-surface)" }}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <SheetHeader className="px-6 pt-6 pb-4 border-b bh-hairline space-y-3 text-left">
            <div className="flex items-center gap-2">
              <PenLine size={16} style={{ color: "var(--bh-brass)" }} />
              <SheetTitle
                className="font-display text-xl font-medium"
                style={{ color: "var(--bh-ink)" }}
              >
                Draft a note
              </SheetTitle>
            </div>
            <SheetDescription className="sr-only">
              Prepare a draft outreach note. Draft-only — nothing sends.
            </SheetDescription>
            <div>
              <div
                className="font-display text-[17px] font-semibold leading-tight"
                style={{ color: "var(--bh-ink)" }}
                data-testid="draft-opp-name"
              >
                {opp.name || opp.company || "Partner"}
              </div>
              <div className="mt-1.5 flex items-center gap-2 flex-wrap">
                <LaneBadge lane={opp.lane || "partner"} />
                <span className="bh-eyebrow">{projectTypeLabel}</span>
                {typeof opp.priority_score === "number" && (
                  <span
                    className="text-[11.5px] font-medium tabular-nums px-2 py-0.5 rounded"
                    style={{
                      background: "var(--bh-brass-mute)",
                      color: "var(--bh-brass)",
                    }}
                    data-testid="draft-lead-score"
                    title={`Score ${Math.round(opp.priority_score)}/100`}
                  >
                    {opp.priority_band === "A" ? "High priority" :
                     opp.priority_band === "B" ? "Medium priority" :
                     "Priority"}
                  </span>
                )}
              </div>
            </div>
            <GuardrailBanner />
          </SheetHeader>

          {/* Scroll body */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            {/* Template selector */}
            <Field label="Playbook">
              <div
                className="grid grid-cols-1 sm:grid-cols-2 gap-2"
                data-testid="playbook-options"
              >
                {options.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => switchPlaybook(p.id)}
                    data-testid={`playbook-${p.audience_slug || p.playbook_id}`}
                    className={
                      "text-left px-3 py-2.5 rounded-md border transition-colors duration-150 " +
                      (selectedId === p.id
                        ? "bh-hairline-warm"
                        : "bh-hairline hover:bg-[var(--bh-surface-2)]/70")
                    }
                    style={
                      selectedId === p.id
                        ? {
                            background: "var(--bh-brass-mute)",
                            borderColor: "var(--bh-hair-warm)",
                          }
                        : {}
                    }
                  >
                    <div
                      className="text-[13.5px] font-medium leading-tight"
                      style={{ color: "var(--bh-ink)" }}
                    >
                      {p.audience_type}
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-[var(--bh-ink-3)] line-clamp-1">
                      {p.name}
                    </div>
                  </button>
                ))}
              </div>
            </Field>

            {/* Personalization panel */}
            <div
              className="rounded-md p-3 space-y-2 text-[12.5px]"
              style={{
                background: "var(--bh-surface-2)",
                border: "1px solid var(--bh-hair)",
              }}
              data-testid="draft-personalization"
            >
              <div className="bh-eyebrow">Personalization</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                <div>
                  <div className="text-[10.5px] text-[var(--bh-ink-3)]">Company</div>
                  <div className="text-[13px]" style={{ color: "var(--bh-ink)" }}>
                    {tokens.company || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10.5px] text-[var(--bh-ink-3)]">Contact</div>
                  <div className="text-[13px]" style={{ color: "var(--bh-ink)" }}>
                    {hasContactName ? tokens.contact_first : "team (no verified name)"}
                  </div>
                </div>
                <div>
                  <div className="text-[10.5px] text-[var(--bh-ink-3)]">Service region</div>
                  <div className="text-[13px]" style={{ color: "var(--bh-ink)" }}>
                    {tokens.service_region || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10.5px] text-[var(--bh-ink-3)]">Opportunity type</div>
                  <div className="text-[13px]" style={{ color: "var(--bh-ink)" }}>
                    {tokens.opportunity_type || "—"}
                  </div>
                </div>
                <div className="col-span-2">
                  <div className="text-[10.5px] text-[var(--bh-ink-3)]">Why this fits</div>
                  <div className="text-[13px]" style={{ color: "var(--bh-ink-2)" }}>
                    {tokens.why_fit || "—"}
                  </div>
                </div>
              </div>
              <div className="pt-1 text-[11px] text-[var(--bh-ink-3)] leading-relaxed">
                Safe variables:{" "}
                <code className="text-[var(--bh-ink-2)]">{`{{company_name}} {{contact_name}} {{service_region}} {{opportunity_type}} {{why_fit}}`}</code>
              </div>
            </div>

            {/* Subject */}
            <Field label="Subject">
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                data-testid="draft-subject"
                className="w-full rounded-md h-10 px-3 text-[14px] bh-hairline"
                style={{
                  background: "var(--bh-surface)",
                  border: "1px solid var(--bh-hair)",
                  color: "var(--bh-ink)",
                }}
                placeholder="Specialty seamless finishes for…"
              />
            </Field>

            {/* Body */}
            <Field
              label="Email body"
              hint={`${body.length} chars`}
            >
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                data-testid="draft-body"
                rows={14}
                className="w-full rounded-md px-3 py-2.5 text-[14px] leading-relaxed resize-y bh-hairline"
                style={{
                  background: "var(--bh-surface)",
                  border: "1px solid var(--bh-hair)",
                  color: "var(--bh-ink-2)",
                  minHeight: "260px",
                }}
                placeholder="Hi team,&#10;&#10;I'm Ryan with The Shirtless Handyman…"
              />
            </Field>

            {/* Internal note */}
            <Field label="Internal note" hint="Not included in copy">
              <textarea
                value={internalNote}
                onChange={(e) => setInternalNote(e.target.value)}
                data-testid="draft-internal-note"
                rows={3}
                className="w-full rounded-md px-3 py-2.5 text-[13px] leading-relaxed resize-y"
                style={{
                  background: "var(--bh-surface-2)",
                  border: "1px solid var(--bh-hair)",
                  color: "var(--bh-ink-2)",
                }}
                placeholder="Context for Ryan before he sends this outside Bloodhound…"
              />
            </Field>

            {/* Review status */}
            <Field label="Review status">
              <div className="flex flex-wrap gap-1.5" data-testid="draft-review-status">
                {REVIEW_STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setReviewStatus(s)}
                    data-testid={`draft-status-${s.toLowerCase().replace(/\s+/g, "-")}`}
                    className={
                      "text-[12px] px-2.5 py-1 rounded-full border transition-colors duration-150 " +
                      (reviewStatus === s
                        ? "bh-hairline-warm"
                        : "bh-hairline hover:bg-[var(--bh-surface-2)]/60")
                    }
                    style={
                      reviewStatus === s
                        ? {
                            background: "var(--bh-brass-mute)",
                            borderColor: "var(--bh-hair-warm)",
                            color: "var(--bh-brass)",
                          }
                        : { color: "var(--bh-ink-3)" }
                    }
                  >
                    {REVIEW_STATUS_LABEL[s] || s}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-[var(--bh-ink-3)] leading-relaxed pt-1">
                &ldquo;Ready to contact&rdquo; records your decision only — it
                does not send anything.
              </p>
            </Field>

            {/* Voice rules (from playbook) */}
            {selected?.voice_rules && (
              <div
                className="rounded-md p-3 text-[12.5px] leading-relaxed"
                style={{
                  background: "var(--bh-surface-2)",
                  border: "1px solid var(--bh-hair)",
                  color: "var(--bh-ink-2)",
                }}
                data-testid="draft-voice-rules"
              >
                <div className="bh-eyebrow mb-1">Voice rules</div>
                {selected.voice_rules}
              </div>
            )}

            {savedDrafts.length > 1 && (
              <div className="text-[11.5px] text-[var(--bh-ink-3)]">
                {savedDrafts.length} saved drafts for this record.
              </div>
            )}
          </div>

          {/* Footer actions */}
          <div className="border-t bh-hairline px-6 py-4 space-y-3">
            <OpenInMessages
              opportunity={{ ...opp, first_message: body || opp.first_message }}
              variant="panel"
            />
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
                <ShieldCheck size={12} style={{ color: "var(--bh-olive)" }} />
                Draft-only workspace
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={discardChanges}
                  data-testid="draft-discard"
                  className="text-[13px] h-9 px-3 rounded-md border bh-hairline"
                  style={{ color: "var(--bh-ink-3)" }}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Trash2 size={13} /> Discard changes
                  </span>
                </button>
                <button
                  onClick={saveDraft}
                  disabled={saving}
                  data-testid="draft-save"
                  className="text-[13px] h-9 px-3 rounded-md border"
                  style={{
                    background: "var(--bh-surface-2)",
                    borderColor: "var(--bh-hair-strong)",
                    color: "var(--bh-ink)",
                  }}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Save size={13} />
                    {saving ? "Saving…" : existingDraftId ? "Update draft" : "Save draft"}
                  </span>
                </button>
                <button
                  onClick={copyToClipboard}
                  data-testid="draft-copy"
                  className="text-[13px] h-9 px-4 rounded-md font-medium"
                  style={{
                    background: "var(--bh-brass)",
                    color: "var(--bh-surface)",
                  }}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Copy size={13} /> Copy draft
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default DraftNoteDrawer;
