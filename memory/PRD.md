# Bloodhound — PRD

## Original Problem Statement
BLOODHOUND — AI Opportunity Intelligence for contractors. Command Center that surfaces qualified leads, partner relationships, and non-permit market signals from a single Airtable base. Palantir/Linear aesthetic, amber/gold accents. Live-connected to Airtable, real outbound email via Emergent-managed Resend, real-time push updates via Airtable webhooks + SSE.

## Architecture
- **Backend**: FastAPI at `/api`, single uvicorn worker.
  - `services/airtable_service.py` — projects Leads → Opportunity DTO. `_derive_lane()` classifies every record into `market_capture` / `partner` / `non_permit`. 45s TTL cache, `typecast=True` writes.
  - `services/leads_service.py` — Leads table with session-level skip/hold/approve, guardrails, email compose/send. Mirrors `_derive_lane_from_lead()` for NBA lane consistency.
  - `services/email_service.py` — Emergent-managed Resend proxy.
  - `services/webhook_service.py` — Airtable webhook registration, HMAC verification, cursor payload polling, in-process SSE broadcaster.
- **Frontend**: React + Tailwind + shadcn/ui.
  - `hooks/useLiveUpdates.js` — EventSource client with auto-reconnect.
  - `components/LaneBadge.jsx` — colored pill (amber / emerald / sky) per lane, used across all pages.
  - `pages/Relationships.jsx` → **Partner Intelligence** (live).
  - `pages/Intelligence.jsx` → **Non-Permit Signals** (live).
  - `pages/CommandCenter.jsx` — lane breakdown strip + Top Opportunities lane tabs + lane badges throughout.
  - `pages/Opportunities.jsx` — Lane filter as the first filter group.

## Implemented
### Core (previously landed)
- Live Airtable projection, ⌘K palette, editable decision panel, priority band / mission derivation, Live Refresh, NBA panel with Approve/Hold/Skip/DNC + draft-message edit, PATCH endpoint hardening, opportunity detail hero grid lock, Approve & Send via Resend with guardrails, Airtable Webhooks + Live SSE push.

### 2026-02-04 — Three-Lane Model
- **Backend**
  - `LANES = ("market_capture", "partner", "non_permit")` with derivation from `Partnership potential` checkbox, `Opportunity type` tokens, `Source category`, and `Source`.
  - Every opportunity + NBA lead DTO now carries `lane` + `lane_label`.
  - `GET /api/opportunities` accepts `lane=` filter.
  - `GET /api/opportunities/lanes` — per-lane counts + pipeline value + top score.
  - `GET /api/opportunities/top-by-lane?limit=N` — top-N per lane ranked by priority score.
  - Sample backend `list()` also accepts `lane=` for local dev.
- **Frontend**
  - **Relationships → Partner Intelligence**: reads `/api/opportunities?lane=partner`. Tabs for Contractors / Designers / Architects / Suppliers / Referral partners derived from `project_type`. Every row shows partner type, relationship status, evidence, source URL, score/confidence, why, and recommended next action. Empty state documents the Airtable-model triggers. Zero outreach controls; "Campaign approval required" pill on every row.
  - **Intelligence → Non-Permit Signals**: reads `/api/opportunities?lane=non_permit`. Platform tabs auto-derived from `source_category`/`source`. Rows show source, signal type, fit, evidence URL, confidence, why, and next action. Empty state explains "A public signal is not permission to contact".
  - **Command Center**: new Lane Breakdown strip (3 clickable cards → lane-filtered opportunities). Top Opportunities gains a lane-tab row (All / Market Capture / Partner Pipeline / Non-Permit Signals). Every opportunity row and mission row shows a `LaneBadge`.
  - **Opportunities**: Lane filter group added as the first filter row.
  - **NBA panel**: lane badge shown next to the lead name.
- All pages remain read-only against Airtable's outreach fields — no outreach send buttons, no automations. Approve & Send lives only on the NBA panel and is unchanged.
- Verified live: `/api/health` → 11 records, `/api/opportunities/lanes` returns `[{market_capture:1 active/11 total, top 62}, {partner:0}, {non_permit:0}]`. Lane filter query returns 11/0/0 respectively — matches your automation's current classification (all rows are Permit-sourced Bathroom leads today; the moment your automation flags a partner or a non-permit source, the corresponding page + card will populate).

## API Reference (dashboard-facing)
```
GET  /api/health
GET  /api/opportunities?lane=&source=&status=&priority_band=&daily_mission=&project_type=&min_score=&q=
GET  /api/opportunities/summary
GET  /api/opportunities/missions
GET  /api/opportunities/pipeline
GET  /api/opportunities/recent?limit=
GET  /api/opportunities/top?limit=
GET  /api/opportunities/top-by-lane?limit=      # NEW
GET  /api/opportunities/lanes                    # NEW
GET  /api/opportunities/{id}
PATCH /api/opportunities/{id}/fields             # writes only status/hunt_status/next_follow_up/outcome/notes/approval_status/outreach_status
GET  /api/leads/next-best-action
POST /api/leads/{id}/action                      # approve / hold / skip / do_not_contact
PATCH /api/leads/{id}/message
POST /api/airtable/webhook                       # signed
GET  /api/live/stream                            # SSE
GET  /api/live/status
POST /api/live/reregister
```

## Airtable Fields In Use (Leads table)
Read: `Leads Name`, `Opportunity type`, `Source`, `Source category`, `Source URL`, `Signal found`, `Address`, `City`, `Permit number`, `Contact name`, `Contact phone`, `Contact email`, `Contact company`, `Contact website`, `Contact instagram`, `Contact facebook`, `Lead score`, `Priority`, `Ai status`, `Ai summary`, `Why lead matters`, `Missing information`, `Risk flags`, `Next action`, `recommended action`, `Recommended offer`, `Outreach angle`, `First message`, `Approval status`, `Outreach status`, `Hunt status`, `Enrichment status`, `Reply summary`, `Reply classification`, `Notes`, `Rejection reason`, `Confidence score`, `contact confidence`, `Best contact method`, `Preferred contact method`, `Outreach channel`, `Revenue potential`, `Estimated job value`, `Closed revenue`, `Estimated gross profit`, `Local service area`, `Bathroom or renovation signal`, `Premium property or client`, `Recent activity`, `Partnership potential`, `Verified opportunity`, `Qualified opportunity`, `Outreach sent`, `Reply received`, `Positive conversation`, `Estimate opportunity`, `Job won`, `Next followup`, `Date contacted`, `Date replied`, `Message sent date`, `Contact data updated`, `Action trigger time`, `Validated at`, `Message generated at`.

Write allowlist: `Status`, `Hunt status`, `Next followup`, `Rejection reason`, `Notes`, `Approval status`, `Outreach status`. Send-side (Approve & Send only): `First message`, `Outreach sent`, `Message sent date`, `Outreach channel`.

## Field Gaps (visible in the UI as "not populated yet")
- `Partnership potential` — never checked in current data → Partner lane empty.
- `Source category` — only value seen is `"Permit"` → Non-Permit lane empty.
- `Opportunity type` — only value seen is `"Bathroom"` → Partner-type tabs all empty.
- `Lead score` / `Confidence score` — 0 on every record → dashboard synthesises a score from richness signals until your automation starts scoring.

## P1 Backlog
- **Slack alerts** for Band A opportunities.
- Twilio/SMS as a second outreach channel once Ryan has a dedicated business number.
- Editable send template + subject line via Settings.
- Persist `webhook_id + mac_secret` to Mongo so a preview restart doesn't leave orphaned webhooks.
- Reply tracking (inbound Resend webhook → Airtable `Reply summary`).

## P2 Backlog
- Auth (JWT or Emergent Google Auth).
- Multi-operator team workspaces.
- Raw Signals table on detail page (permit chain).
- Guard `typecast=True` server-side so status typos can't pollute Airtable options.
- Dedupe airtable_service + leads_service connection code.
- CSV export + weekly digest email.

## Known Advisories
- Leads service in-memory skip/hold/approve state diverges under multi-worker uvicorn (single-worker today).
- Webhook secret + cursor + id live in memory — on restart the webhook is deleted + re-created (idempotent).
- Airtable webhooks last 7 days by default; no refresh cron yet — re-registered on every backend restart.
- Preview + production run different backend URLs. Change `PUBLIC_BACKEND_URL` before deploy and use `/api/live/reregister` after.
