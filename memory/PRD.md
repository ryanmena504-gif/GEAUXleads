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
- **Needs confirmation banner** on detail page when outreach history exists
  but status is still ambiguous.
- **No auto-save on draft open**: writes gated by EDITABLE_FIELDS allowlist.
- **AI Contact Enrichment (NEW · 2026-02-11)** — Manual sweep from Settings.
  - Uses Gemini 2.5 Flash + Google Search grounding (via Emergent LLM Key +
    `emergentintegrations`).
  - Targets only leads missing BOTH phone and email (and not blocked/closed).
  - Writes verified public phone/email/website back to Airtable via the
    EDITABLE_FIELDS allowlist (`Contact phone`, `Contact email`,
    `Contact website` were added).
  - Leads 5+ days old with no results get soft-archived by setting
    Outreach status = "Archived — no contact found".
  - Toggle in Settings gates the "Enrich now" button. Async background task
    (POST returns 202 immediately, frontend polls /api/enrichment/status).
  - Cap: 15 leads per sweep.
  - Verified end-to-end 2026-02-11: sweep scanned 17 → enriched 5 → archived
    12 → failed 0.

## Recent changelog
- 2026-02-11 — AI Contact Enrichment feature shipped. New service
  `enrichment_service.py`, endpoints `GET /api/enrichment/status` +
  `POST /api/enrichment/run`, `enrichment_enabled` user setting,
  Settings section with toggle + Enrich-now button + last-run stats.
- 2026-02-11 — Rewrote CommandCenter into strict 3-section Today page,
  added contactReady/hasPremiumFit/needsConfirmation helpers, fixed
  `_derive_status` in airtable_service to honor `outreach_status`.
- 2026-02 (prior sessions) — 4-item nav · POST /api/opportunities/{id}/result ·
  handoff logger · sender-identity settings · WonThisMonth KPI · Time-to-Nudge.

## Backlog
### P1 — Per-lead enrichment
- Add a per-lead "Find contact" button on the OpportunityDetail page so Ryan
  can enrich one lead on demand without running a full sweep.
- Add a Settings knob for `max_per_sweep` (currently hardcoded to 15).

### P2 — Webhook persistence
- Persist Airtable webhook state to Mongo so preview reloads don't hijack the
  production webhook.

### P3 — Small polish
- Add a reason chip on Today Section 1 rows (parity with Section 2's yellow pill).
- Consider unifying BottomNav testids to `nav-*` prefix (currently `bottomnav-*`).
- Restore soft-archived leads action: a "Retry enrichment" button on archived
  leads to clear the flag and re-scan.

## Files of interest
- `/app/frontend/src/pages/CommandCenter.jsx` — 3-section Today page.
- `/app/frontend/src/pages/OpportunityDetail.jsx` — manual result buttons +
  Needs-confirmation banner.
- `/app/frontend/src/pages/Settings.jsx` — SenderIdentity + EnrichmentSection.
- `/app/frontend/src/lib/priority.js` — contactReady / hasPremiumFit /
  needsConfirmation.
- `/app/frontend/src/components/Sidebar.jsx` + `BottomNav.jsx` — 4 items.
- `/app/backend/server.py` — /api/opportunities/{id}/result, /kpis/monthly,
  /follow-ups/due, /handoff, /settings/user, /enrichment/status,
  /enrichment/run.
- `/app/backend/services/airtable_service.py` — read/write to Leads;
  EDITABLE_FIELDS now includes Contact phone/email/website.
  `_derive_status` honors outreach_status.
- `/app/backend/services/enrichment_service.py` — Gemini 2.5 Flash +
  Google Search grounding sweep, soft-archive logic.
- `/app/backend/services/user_settings_service.py` — settings singleton with
  `enrichment_enabled` toggle.
