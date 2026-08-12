# BLOODHOUND — AI Opportunity Intelligence · PRD

## Original problem
A premium full-stack app for contractors (Ryan) that discovers, understands, and
prioritizes business opportunities and partners. Airtable `Leads` table is the
source of truth. Everything outbound is **native iOS handoff only** (`sms:` and
`mailto:`). **No automated backend sending** (no Resend, Twilio, Gmail APIs).

## Product principles
- Plain English everywhere. Hide scores/bands/database jargon.
- Manual result buttons are the ONLY way outreach status advances.
- Opening a draft NEVER writes to Airtable.
- Records are NEVER dropped, archived, hidden, or retired because contact
  info is missing. The AI keeps learning from the same set.
- Ryan's identity is locked; other users are read-only.

## Core requirements (implemented)
- **4-item navigation** (Sidebar + BottomNav): Today · All Projects · People to
  Know · Settings.
- **Today page = exactly 3 work buckets** (above them: a "Won this month" KPI
  strip):
  1. **Contact Now** — strict gate: verified public BUSINESS phone/email +
     premium fit + source URL + date checked + no history conflict + NOT
     a homeowner/permit-address contact.
  2. **Watch** — every active lead that doesn't meet the Contact Now bar
     (includes leads with a "No public business contact found yet" note).
     Nothing here is ever dropped.
  3. **Not a Fit** — Disqualified / Lost / Do Not Contact / Not Interested.
     Kept visible so nothing is forgotten; never contacted.
- **Manual result buttons** on `/opportunities/:id` (sent, replied,
  estimate_requested, no_reply, not_interested). Opening a draft NEVER
  triggers these.
- **Needs confirmation banner** when outreach history is ambiguous.
- **AI Contact Enrichment** — Manual only. Toggle defaults OFF.
  - Model: Gemini 2.5 Flash + Google Search grounding (Emergent LLM Key +
    `emergentintegrations`).
  - Target pool: leads missing BOTH phone AND email that are still active.
  - Business/professional contacts only. Homeowner / private / permit-
    address contacts are explicitly rejected in the prompt.
  - Outcomes per record: `contact_found` · `no_public_business_contact` ·
    `needs_review`.
  - No-hit records get: Notes ← "No public business contact found yet ·
    checked YYYY-MM-DD"; Next followup ← today + 30 days. Never archived.
  - Never touches: SMS Permission, Outreach sent, Message sent date,
    Conversation started, or any result field.
  - Sweep cap: 15 leads per manual run.
  - Per-lead **"Find public business contact"** button on the detail page
    (confirmation required before running).

## Recent changelog
- 2026-02-11 (final) — Removed 5-day soft-archive rule entirely; added 3-
  bucket Today page (Contact Now / Watch / Not a Fit); tightened the LLM
  prompt to reject homeowner/private/permit-address contacts; added
  30-day recheck marking on no-hit records; added confirmation modal to
  the per-lead enrichment button; renamed button to "Find public business
  contact"; restored 22 previously affected records to Watch with
  `Outreach status = Not sent`, notes tag, and next-recheck date.
- 2026-02-11 — Per-lead enrichment button + backend endpoint.
- 2026-02-11 — AI Contact Enrichment sweep shipped.
- 2026-02-11 — Rewrote CommandCenter into strict 3-section Today page;
  contactReady / hasPremiumFit / needsConfirmation / isBusinessContact /
  isClosedOrBlocked helpers.

## Backlog
### P1 — Recheck-driven surfacing
- Highlight records whose 30-day recheck date has passed as a Watch
  sub-bucket ("ready for another look") — surfaced only when Ryan opens
  Watch; still never runs enrichment automatically.

### P2 — Webhook persistence
- Persist Airtable webhook state to Mongo so preview reloads don't hijack
  the production webhook.

### P3 — Small polish
- Add a source URL + reason chip to each Contact Now row.
- Unify BottomNav testids to `nav-*` prefix.

## Files of interest
- `/app/frontend/src/pages/CommandCenter.jsx` — 3-bucket Today (Contact
  Now / Watch / Not a Fit).
- `/app/frontend/src/pages/OpportunityDetail.jsx` — manual result buttons,
  Needs confirmation banner, "Find public business contact" button with
  confirmation.
- `/app/frontend/src/pages/Settings.jsx` — SenderIdentity + Enrichment
  toggle + Enrich-now sweep button.
- `/app/frontend/src/lib/priority.js` — contactReady, hasPremiumFit,
  needsConfirmation, isBusinessContact, isClosedOrBlocked.
- `/app/backend/server.py` — endpoints /result, /enrich, /enrichment/run,
  /enrichment/status, /settings/user.
- `/app/backend/services/airtable_service.py` — EDITABLE_FIELDS gate;
  `_derive_status` honors outreach_status.
- `/app/backend/services/enrichment_service.py` — Gemini sweep with
  business-only prompt; 30-day recheck writes; three-way outcome enum.
