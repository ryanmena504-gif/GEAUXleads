import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PenLine, Save, RotateCcw, ShieldCheck, BookMarked } from "lucide-react";
import { api } from "@/lib/api";

/**
 * PlaybookEditor — Settings section that lets Ryan tweak the Default Subject
 * and Default Draft of every playbook without opening Airtable. Only those
 * two fields are editable client-side, and the server enforces the same
 * allowlist. Everything else (Audience Type, Voice Rules, Status, …) stays
 * managed inside Airtable.
 */
const AUDIENCE_LABEL = {
  builder: "Builder / Remodeler",
  designer: "Interior Designer",
  pool_outdoor: "Pool / Outdoor Living",
};

const PlaybookCard = ({ playbook, onSaved }) => {
  const initialSubject = playbook.default_subject || "";
  const initialBody = playbook.default_draft || "";
  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState(initialBody);
  const [saving, setSaving] = useState(false);

  // Keep local state fresh when the parent refetches
  useEffect(() => {
    setSubject(playbook.default_subject || "");
    setBody(playbook.default_draft || "");
  }, [playbook.id, playbook.default_subject, playbook.default_draft]);

  const dirty = subject !== initialSubject || body !== initialBody;

  const save = async () => {
    if (!dirty) return;
    setSaving(true);
    try {
      const updated = await api.updatePlaybook(playbook.id, {
        default_subject: subject,
        default_draft: body,
      });
      toast.success(`"${playbook.audience_type}" playbook saved to Airtable`);
      onSaved(updated);
    } catch {
      toast.error("Save failed — Airtable rejected the update");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setSubject(initialSubject);
    setBody(initialBody);
  };

  const badge =
    AUDIENCE_LABEL[playbook.audience_slug] || playbook.audience_type || "Custom";

  return (
    <div
      className="bh-surface rounded-md p-5 space-y-4"
      data-testid={`playbook-card-${playbook.audience_slug || playbook.id}`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <BookMarked size={13} style={{ color: "var(--bh-brass)" }} />
            <span
              className="bh-eyebrow"
              style={{ color: "var(--bh-brass)" }}
            >
              {badge}
            </span>
            {playbook.channel && (
              <span className="text-[11px] text-[var(--bh-ink-3)]">· {playbook.channel}</span>
            )}
          </div>
          <div
            className="mt-1 font-display text-[15px] font-semibold truncate"
            style={{ color: "var(--bh-ink)" }}
          >
            {playbook.name}
          </div>
        </div>
        {dirty && (
          <span
            className="text-[11px] px-2 py-0.5 rounded-full border whitespace-nowrap"
            style={{
              background: "var(--bh-brass-mute)",
              color: "var(--bh-brass)",
              borderColor: "var(--bh-hair-warm)",
            }}
            data-testid={`playbook-dirty-${playbook.audience_slug || playbook.id}`}
          >
            Unsaved changes
          </span>
        )}
      </div>

      <div>
        <label className="bh-eyebrow block mb-1.5">Default subject</label>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          data-testid={`playbook-subject-${playbook.audience_slug || playbook.id}`}
          className="w-full rounded-md h-10 px-3 text-[14px]"
          style={{
            background: "var(--bh-surface)",
            border: "1px solid var(--bh-hair)",
            color: "var(--bh-ink)",
          }}
        />
      </div>

      <div>
        <div className="flex items-baseline justify-between mb-1.5">
          <label className="bh-eyebrow">Default draft body</label>
          <span className="text-[11px] text-[var(--bh-ink-3)]">
            {body.length} chars
          </span>
        </div>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          data-testid={`playbook-body-${playbook.audience_slug || playbook.id}`}
          rows={12}
          className="w-full rounded-md px-3 py-2.5 text-[13.5px] leading-relaxed resize-y"
          style={{
            background: "var(--bh-surface)",
            border: "1px solid var(--bh-hair)",
            color: "var(--bh-ink-2)",
            minHeight: "220px",
          }}
        />
        {playbook.editable_variables && (
          <p className="mt-1.5 text-[11px] text-[var(--bh-ink-3)] leading-relaxed">
            Variables: <code className="text-[var(--bh-ink-2)]">{playbook.editable_variables}</code>
          </p>
        )}
      </div>

      {playbook.voice_rules && (
        <div
          className="rounded-md p-3 text-[12px] leading-relaxed"
          style={{
            background: "var(--bh-surface-2)",
            border: "1px solid var(--bh-hair)",
            color: "var(--bh-ink-3)",
          }}
        >
          <span className="bh-eyebrow mr-1.5">Voice rules</span>
          {playbook.voice_rules}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 flex-wrap pt-1">
        <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
          <ShieldCheck size={12} style={{ color: "var(--bh-olive)" }} />
          Writes only Default Subject + Default Draft. Nothing else in Airtable is touched.
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={reset}
            disabled={!dirty || saving}
            data-testid={`playbook-reset-${playbook.audience_slug || playbook.id}`}
            className="text-[12.5px] h-9 px-3 rounded-md border bh-hairline inline-flex items-center gap-1.5 disabled:opacity-40"
            style={{ color: "var(--bh-ink-3)" }}
          >
            <RotateCcw size={12} /> Reset
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!dirty || saving}
            data-testid={`playbook-save-${playbook.audience_slug || playbook.id}`}
            className="text-[13px] h-9 px-4 rounded-md font-medium inline-flex items-center gap-1.5 disabled:opacity-40"
            style={{
              background: "var(--bh-brass)",
              color: "var(--bh-surface)",
            }}
          >
            <Save size={13} />
            {saving ? "Saving…" : "Save to Airtable"}
          </button>
        </div>
      </div>
    </div>
  );
};

export const PlaybookEditor = () => {
  const [playbooks, setPlaybooks] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await api.listPlaybooks();
      setPlaybooks(res?.playbooks || []);
    } catch {
      setPlaybooks([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onSaved = (updated) => {
    setPlaybooks((list) =>
      (list || []).map((p) => (p.id === updated.id ? { ...p, ...updated } : p)),
    );
  };

  if (playbooks === null) {
    return (
      <div className="bh-surface rounded p-8 text-center text-[13px] text-[var(--bh-ink-3)]">
        Loading playbooks…
      </div>
    );
  }
  if (playbooks.length === 0) {
    return (
      <div className="bh-surface rounded p-8 text-center text-[13px] text-[var(--bh-ink-3)]">
        No playbooks in Airtable yet.
      </div>
    );
  }
  return (
    <div className="space-y-3" data-testid="playbook-editor">
      <div
        className="rounded-md px-3 py-2 text-[12px] flex items-start gap-2"
        style={{
          background: "var(--bh-brass-mute)",
          border: "1px solid var(--bh-hair-warm)",
          color: "var(--bh-ink-2)",
        }}
      >
        <PenLine size={12} className="mt-0.5" style={{ color: "var(--bh-brass)" }} />
        <span>
          Edits sync back to the Airtable <em>Message Playbooks</em> table so
          the Draft a Note drawer picks them up on the next open. Audience
          type, channel, and voice rules stay managed inside Airtable.
        </span>
      </div>
      {playbooks.map((p) => (
        <PlaybookCard key={p.id} playbook={p} onSaved={onSaved} />
      ))}
    </div>
  );
};

export default PlaybookEditor;
