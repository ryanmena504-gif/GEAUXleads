import React, { useCallback, useState } from "react";
import { Phone, Mail, Check } from "lucide-react";
import { toast } from "sonner";
import ResearchPanel from "@/components/ResearchPanel";
import { api } from "@/lib/api";
import { extractEmail, extractPhone } from "@/lib/contactExtract";

/**
 * Owner-contact research for permit/homeowner leads.
 *
 * Runs the `owner_contact` Perplexity research (owner name + property
 * address), extracts any phone/email the bot found, and offers one-tap
 * save buttons that write them onto the lead via PATCH /fields.
 * Nothing writes to Airtable until Ryan taps Save — the research
 * itself is read-only.
 */
const OwnerContactResearch = ({ opp, onUpdated }) => {
  const [found, setFound] = useState(null);
  const [saving, setSaving] = useState("");

  const ownerName = opp?.owner || opp?.applicant || "";
  const address = opp?.project_address || opp?.name || "";

  const handleResult = useCallback(
    (result) => {
      const answer = result?.answer || "";
      const phone = extractPhone(answer);
      const email = extractEmail(answer);
      setFound({ phone, email, ran: true });
    },
    []
  );

  const save = useCallback(
    async (field, value) => {
      if (!value) return;
      setSaving(field);
      try {
        const updated = await api.updateFields(opp.id, { [field]: value });
        onUpdated?.(updated);
        setFound((prev) => (prev ? { ...prev, [field]: null } : prev));
        toast.success(
          field === "phone" ? "Phone saved to lead" : "Email saved to lead"
        );
      } catch (err) {
        toast.error(err?.response?.data?.detail || "Could not save that contact");
      } finally {
        setSaving("");
      }
    },
    [opp?.id, onUpdated]
  );

  const query =
    `Property owner contact lookup. Owner name: ${ownerName || "(unknown)"}. ` +
    `Property address: ${address || "(unknown)"}. ` +
    `Applicant on permit: ${opp?.applicant || "(none)"}. ` +
    `Contractor on record: ${opp?.contractor || "(none)"}. ` +
    `Find any publicly listed phone number or email for this owner.`;

  const showPhoneSave = found?.phone && found.phone !== opp?.phone;
  const showEmailSave = found?.email && found.email !== opp?.email;

  return (
    <div className="mt-4">
      <ResearchPanel
        researchType="owner_contact"
        recordId={opp.id}
        query={query}
        onResult={handleResult}
        label={opp?.phone || opp?.email ? "Re-check owner contact" : "Find owner contact"}
        hint="Researches the property owner for a public phone/email. Read-only until you tap Save."
        testId={`research-owner-contact-${opp.id}`}
      />
      {found?.ran && (
        <div className="mt-2 space-y-2" data-testid={`owner-contact-found-${opp.id}`}>
          {(showPhoneSave || showEmailSave) ? (
            <>
              {showPhoneSave && (
                <div className="flex items-center justify-between gap-2 rounded-md border bh-hairline px-3 py-2">
                  <span className="flex items-center gap-2 text-[13px]">
                    <Phone size={13} className="text-[var(--bh-brass)]" />
                    <span className="mono">{found.phone}</span>
                  </span>
                  <button
                    type="button"
                    disabled={saving === "phone"}
                    onClick={() => save("phone", found.phone)}
                    data-testid={`owner-contact-save-phone-${opp.id}`}
                    className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--bh-brass)] hover:underline disabled:opacity-50"
                  >
                    <Check size={12} />
                    {saving === "phone" ? "Saving…" : "Save phone"}
                  </button>
                </div>
              )}
              {showEmailSave && (
                <div className="flex items-center justify-between gap-2 rounded-md border bh-hairline px-3 py-2">
                  <span className="flex items-center gap-2 text-[13px] min-w-0">
                    <Mail size={13} className="text-[var(--bh-brass)] shrink-0" />
                    <span className="mono truncate">{found.email}</span>
                  </span>
                  <button
                    type="button"
                    disabled={saving === "email"}
                    onClick={() => save("email", found.email)}
                    data-testid={`owner-contact-save-email-${opp.id}`}
                    className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--bh-brass)] hover:underline disabled:opacity-50"
                  >
                    <Check size={12} />
                    {saving === "email" ? "Saving…" : "Save email"}
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="text-[12px] text-[var(--bh-ink-3)]">
              {found.phone || found.email
                ? "Found contact matches what's already on file."
                : "No public phone or email found for this owner."}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default OwnerContactResearch;
