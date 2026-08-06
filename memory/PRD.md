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

### 2026-02-04 — Lead Score Canonical Ranking
- `sort_opportunities()` is the single source of truth for ranking. Modes: `lead_score` (default, DESC), `freshness`, `confidence`. Scored records always precede unscored; ties by freshness DESC then id ASC.
- `_derive_priority_score()` reads Airtable's cleaned `Lead score` only — never synthesised, returns None when missing.
- NBA (`pick_next_best_action`) picks the top absolute `lead_score` across the eligible queue.
- Frontend Opportunities page adds a `Lead Score / Freshness / Confidence` sort control; selection is persisted to the URL (`?sort=`).
- Verified by testing agent iteration_7: 15/15 backend + full frontend sort UI pass, Command Center top-opps prefix perfectly matches `/api/opportunities/top`.

### 2026-02-04 — Hunt-Status Guardrail Fix
- `LEADS_FIELD_MAP` now maps Airtable `Hunt status` → `hunt_status`. `can_send()` correctly returns 422 with `Blocked by Hunt status=...` when the field contains `rejected/closed/disqualified`. Verified: no email leaves Resend when guardrail fires.

### 2026-02-04 — Light Premium UI Polish
- Command Palette (⌘K) rewired to the bone/limestone/graphite palette: `bh-eyebrow` group headings, `--bh-ink` text tokens, `--bh-brass` accent on quick-filter icons. No more dark `text-neutral-*` remnants.
- OpportunityDetail KV labels already use sentence-case via `.bh-eyebrow` (`text-transform:none`).

### 2026-02-04 — Slack Band A Alerts (Incoming Webhook)
- **Endpoint / trigger**: after every Airtable webhook ping, the SSE broadcaster also scans currently Band-A opportunities and dispatches Slack notifications.
- **Dedupe (Mongo)**: collection `slack_band_a_alerts` persists `{opportunity_id, last_alerted_score, alert_sent_at, alert_count, last_reason}`. A lead is alerted at most once unless its `Lead score` climbs by **10 points or more** after the prior alert.
- **Payload**: Slack Block Kit — header + lead name + fields (Lead score, Confidence, Lane, Source, Location) + Why it matters + Next best action + "Open in Bloodhound" button + "Notification only · no outreach triggered" context.
- **Secrecy**: webhook URL read from `SLACK_BLOODHOUND_WEBHOOK_URL` env at call time. Never logged, never returned by any API, never exposed to the frontend. On success/failure only the HTTP status code is logged, not the body.
- **Fail-safe**: absent env var → single boot-time warning, app remains fully functional, all endpoints unaffected.
- **API**: `GET /api/slack/alerts/status` returns `{configured, score_delta_threshold, tracked_alerts_total, last_alert}` (no URL). `POST /api/slack/alerts/scan` re-scans Band A and dispatches any missed alerts (idempotent via dedupe).
- Verified: 6/6 unit tests in `backend/tests/slack_service_test.py` pass — new-lead / below-delta / at-delta / missing-scores / Band B never fires / block payload correctness.

## API Reference (dashboard-facing)
```
GET  /api/health
GET  /api/opportunities?lane=&source=&status=&priority_band=&daily_mission=&project_type=&min_score=&q=&sort=
GET  /api/opportunities/summary
GET  /api/opportunities/missions
GET  /api/opportunities/pipeline
GET  /api/opportunities/recent?limit=
GET  /api/opportunities/top?limit=
GET  /api/opportunities/top-by-lane?limit=
GET  /api/opportunities/lanes
GET  /api/opportunities/{id}
PATCH /api/opportunities/{id}/fields             # writes only status/hunt_status/next_follow_up/outcome/notes/approval_status/outreach_status
GET  /api/leads/next-best-action
POST /api/leads/{id}/action                      # approve / hold / skip / do_not_contact
PATCH /api/leads/{id}/message
POST /api/airtable/webhook                       # signed
GET  /api/live/stream                            # SSE
GET  /api/live/status
POST /api/live/reregister
GET  /api/slack/alerts/status                    # NEW — never returns URL
POST /api/slack/alerts/scan                      # NEW — idempotent Band A backfill
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
- Twilio/SMS as a second outreach channel once Ryan has a dedicated business number.
- Editable send template + subject line via Settings.
- Persist `webhook_id + mac_secret` to Mongo so a preview restart doesn't leave orphaned webhooks.
- Reply tracking (inbound Resend webhook → Airtable `Reply summary`).
- Slack alert digest: rollup + morning summary in addition to per-lead pings.

## SMS Permission field (2026-02-06)
- Added `SMS Permission → sms_permission` to both `airtable_service.LEADS_FIELD_MAP` (opportunity DTO) and `leads_service.LEADS_FIELD_MAP` (NBA DTO). Marked read-only in `EXPLICIT_READONLY` so the app never writes it — the field is authored in Airtable.
- Backend `_has_sms_permission()` is now STRICT: the record's `sms_permission` value must equal `Yes`, `Existing Customer`, or `Warm Relationship`. Every other value (No, Unknown, blank, missing field) blocks the SMS draft.
- Frontend `DraftNoteDrawer` mirrors the same strict check client-side: the "Create SMS draft in Airtable" panel only appears when the record has both a phone and an explicit permitted value.
- **Airtable field creation blocked at 403** — the personal access token lacks `schema.bases:write`. The user needs to either grant that scope to the PAT or add the field manually in the Airtable UI (single-select with options Yes / Existing Customer / Warm Relationship / No / Unknown). Once the field exists with a permitted value on any lead, the SMS panel appears automatically — no code change needed.

## Draft a Note (2026-02-05)
- Server-side `GET /api/message-playbooks` reads the Airtable `Message Playbooks` table (tble13PxRqtWfPHzb) and returns a safe UI DTO with no credentials.
- Mongo-backed `outreach_drafts` collection with full CRUD at `/api/drafts` (`opportunity_id`, `selected_playbook`, `subject`, `body`, `internal_note`, `review_status`, timestamps). Persists across refresh — verified via e2e Playwright: save with a marker, reload page, reopen drawer, marker still in subject + body + "Ready for Ryan review" pill still active.
- `POST /api/opportunities/{id}/sms-draft` appends a timestamped SMS draft to Airtable Notes with `Outreach status = "SMS Draft"`. Requires `confirmed=true`, a permitted business phone, and an SMS permission hint. **Never sends SMS.**
- Right-side drawer (`DraftNoteDrawer.jsx`) shows opportunity header, lane badge, Lead Score, guardrail banner, playbook selector (auto-picks Builder/Designer/Pool from `project_type` + company name + evidence, plus "Start from blank"), personalization panel, editable subject + body, internal note, review-status pills, Copy/Save/Discard, and a conditional "Create SMS draft in Airtable" panel.
- **Auto-select heuristic** (`audienceFromOpportunity`): matches on project_type + name + why-fit — so "Backyard Living" (project_type=Contractor) still routes to **Pool / Outdoor Living**. Precedence: pool/outdoor > designer/architect > contractor/remodeler.
- Wired button `Draft a Note` in **three** placements:
  - `OpportunityDetail.jsx` — directly below `Mark Contacted` when `lane === "partner"`
  - `Relationships.jsx` → PartnerRow — inline `[Draft a Note]` pill next to Source
  - `NextBestAction.jsx` — next to `Approve & Send` when the picked lead is in Partner Pipeline
- Verified with the 4 required records: **Sweeney Restoration** → Builder/Remodeler, **Tristan Construction LLC** → Builder/Remodeler, **Walther Design Studio** → Interior Designer, **Backyard Living** → Pool / Outdoor Living.
- Guardrail scan clean: no send / mail / SMS / DM / webhook call from this feature. The only outbound work is copy-to-clipboard and safe Airtable Notes writes (through the existing write allowlist).

## Environment
- `SLACK_BLOODHOUND_WEBHOOK_URL` (secret) — enables Band A Slack alerts. Absent → alerts skipped, boot warns once, everything else works.
- `PUBLIC_APP_URL` (optional) — frontend base URL used in the "Open in Bloodhound" button. Falls back to `PUBLIC_BACKEND_URL`.

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
