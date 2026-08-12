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
  1. People to contact today — strict contact-ready gate: verified public phone
     or email + premium-fit evidence + source URL + date checked + no history
     conflict.
  2. Projects to watch — premium fit but no verified phone/email yet.
  3. People to know — partners (lane=partner) preview → link to /relationships.
- **Manual result buttons** on `/opportunities/:id`:
  - `sent` → Outreach status="Sent by Ryan" · status intentionally NOT advanced
  - `replied` → Outreach status="Reply received" · status="Conversation started"
  - `estimate_requested` → status="Estimate requested"
  - `no_reply` → Outreach status="No reply yet" · status unchanged
  - `not_interested` → Outreach status="Not interested" · status="Disqualified"
- **Needs confirmation banner** on detail page: shown when the record has
  outreach history (flag_outreach_sent OR outreach_status contains sent/reply/
  no reply) AND status is still ambiguous (New / Needs research / Ready).
- **No auto-save on draft open**: writes are gated by `EDITABLE_FIELDS`
  allowlist in `airtable_service.py`; handoff endpoint writes to Mongo only.
- **Follow-up sequencing** ("Time to nudge") + monthly KPIs endpoint exist and
  are usable across the app (still surfaced within detail flow / kpi strip).

## Recent changelog
- 2026-02-11 — Feature branch `feature/bloodhound-production-cleanup`
  - Rewrote `CommandCenter.jsx` into strict 3-section layout.
  - Added `contactReady`, `hasPremiumFit`, `needsConfirmation` helpers in
    `frontend/src/lib/priority.js`.
  - Added Needs confirmation banner to `OpportunityDetail.jsx`.
  - Fixed `_derive_status` in `airtable_service.py` to honor `outreach_status`
    so manual result taps (replied/not_interested/estimate_requested) are not
    silently overridden by other signal flags on the read path.
- 2026-02 (prior sessions) — 4-item nav rewired · POST /api/opportunities/{id}/
  result endpoint · handoff logger (Mongo) · sender-identity settings ·
  WonThisMonth KPI strip · Time-to-Nudge follow-ups.

## Backlog
### P1 — AI contact enrichment
- Daily background sweep using Emergent LLM Key + Gemini with Google Search
  grounding to fill missing phone/email fields on `Leads`.
- 5-day soft-archive of leads that stay empty.

### P2 — Webhook persistence
- Persist Airtable webhook state to Mongo so preview reloads don't hijack the
  production webhook.

### P3 — Small polish
- Add a reason chip on Section 1 rows (parity with Section 2's yellow pill).
- Consider unifying BottomNav testids to `nav-*` prefix (currently
  `bottomnav-*`).
- `outreach_status` in FieldUpdate model is intentionally omitted — it is
  only writable via POST /result. Document this in the OpenAPI/README.

## Files of interest
- `/app/frontend/src/pages/CommandCenter.jsx` — 3-section Today page.
- `/app/frontend/src/pages/OpportunityDetail.jsx` — manual result buttons +
  Needs-confirmation banner.
- `/app/frontend/src/lib/priority.js` — contactReady / hasPremiumFit /
  needsConfirmation.
- `/app/frontend/src/components/Sidebar.jsx` + `BottomNav.jsx` — 4 items.
- `/app/backend/server.py` — /api/opportunities/{id}/result, /kpis/monthly,
  /follow-ups/due, /handoff, /settings/user.
- `/app/backend/services/airtable_service.py` — read/write to Leads; strict
  EDITABLE_FIELDS allowlist. `_derive_status` now honors outreach_status.
