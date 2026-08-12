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
- Strict "Contact ready" evidence gate on the Today page.
- Ryan's identity is locked; other users are read-only.

## Core requirements (implemented)
- **4-item navigation** (Sidebar + BottomNav): Today · All Projects · People to
  Know · Settings.
- **Today page = exactly 3 sections** (above them: a "Won this month" KPI strip):
  1. People to contact today — strict contact-ready gate.
  2. Projects to watch — premium fit but no verified phone/email yet.
  3. People to know — partners preview → link to /relationships.
- **Manual result buttons** on `/opportunities/:id` (sent, replied,
  estimate_requested, no_reply, not_interested).
- **Needs confirmation banner** when outreach history exists but status is
  still ambiguous.
- **No auto-save on draft open**.
- **AI Contact Enrichment (2026-02-11)** — Manual sweep from Settings +
  per-lead "Find contact" button on the detail page.
  - Gemini 2.5 Flash + Google Search grounding (via Emergent LLM Key +
    `emergentintegrations`).
  - Full sweep: targets leads missing BOTH phone and email, caps at 15 per
    sweep, soft-archives leads 5+ days old with no result.
  - Per-lead: "Find contact" button in the Who-to-talk-to section — shows
    only when both phone AND email are blank. Respects the same
    enrichment_enabled toggle. Toasts back exactly what was found.
  - Writes verified public phone/email/website to Airtable via the
    EDITABLE_FIELDS allowlist (`Contact phone`, `Contact email`,
    `Contact website`).
  - Async job pattern: POST returns 202, frontend polls status.

## Recent changelog
- 2026-02-11 — Per-lead "Find contact" button (endpoint
  `POST /api/opportunities/{id}/enrich`, `enrichment_service.enrich_lead()`).
- 2026-02-11 — AI Contact Enrichment sweep shipped
  (`services/enrichment_service.py`, /api/enrichment/status + /run,
  Settings section, `enrichment_enabled` user setting).
- 2026-02-11 — Rewrote CommandCenter into strict 3-section Today page,
  contactReady/hasPremiumFit/needsConfirmation helpers, fixed
  `_derive_status` to honor outreach_status.
- 2026-02 (prior sessions) — 4-item nav, manual result endpoint, handoff
  logger, sender-identity settings, WonThisMonth KPI, Time-to-Nudge.

## Backlog
### P1 — Archive reset
- "Retry enrichment" button on soft-archived leads to clear the flag and
  re-scan (in case Gemini missed a source it can find later).
- Settings knob for `max_per_sweep` (currently hardcoded to 15).

### P2 — Webhook persistence
- Persist Airtable webhook state to Mongo so preview reloads don't hijack the
  production webhook.

### P3 — Small polish
- Reason chip on Today Section 1 rows for parity with Section 2's yellow pill.
- Unify BottomNav testids to `nav-*` prefix.

## Files of interest
- `/app/frontend/src/pages/CommandCenter.jsx` — 3-section Today page.
- `/app/frontend/src/pages/OpportunityDetail.jsx` — manual result buttons +
  Needs-confirmation banner + Find-contact button.
- `/app/frontend/src/pages/Settings.jsx` — SenderIdentity + EnrichmentSection.
- `/app/frontend/src/lib/priority.js` — contactReady / hasPremiumFit /
  needsConfirmation.
- `/app/frontend/src/lib/api.js` — includes `enrichLead(id)`.
- `/app/frontend/src/components/Sidebar.jsx` + `BottomNav.jsx` — 4 items.
- `/app/backend/server.py` — result / kpis / follow-ups / handoff / settings /
  enrichment endpoints (sweep + per-lead).
- `/app/backend/services/airtable_service.py` — EDITABLE_FIELDS includes
  Contact phone/email/website. `_derive_status` honors outreach_status.
- `/app/backend/services/enrichment_service.py` — `run_sweep()` + `enrich_lead()`.
- `/app/backend/services/user_settings_service.py` — `enrichment_enabled` key.
