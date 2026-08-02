# Bloodhound — PRD

## Original Problem Statement
Build a premium full-stack web application called BLOODHOUND — AI Opportunity Intelligence for contractors. Command Center that helps discover, understand, and prioritize business opportunities before competitors. Dark, high-end, Palantir/Linear aesthetic with amber/gold accents. Reads live from Airtable and allows approved-field writes back. Approve & Send actually delivers email through Emergent-managed Resend. New Airtable rows and edits appear on the dashboard within ~1 second via Airtable webhooks + SSE push.

## Architecture
- **Backend**: FastAPI at `/api`, single uvicorn worker.
  - `services/airtable_service.py` — projects the live `Leads` Airtable table into the Opportunity DTO. 45s TTL cache, `typecast=True` writes, `AirtableWriteError` for graceful 4xx propagation.
  - `services/leads_service.py` — same Leads table, NBA queue with session-level skip/hold/approve, strict write-allowlist, `can_send()` guardrails, `compose_email()`, `mark_sent()`.
  - `services/email_service.py` — Emergent-managed Resend proxy; async send, `EmailSendError` with upstream status code.
  - `services/webhook_service.py` — **NEW**: Airtable Webhook manager. Idempotent registration, HMAC signature verification, cursor-based payload polling, in-process asyncio broadcaster for SSE fan-out.
- **Frontend**: React + Tailwind + shadcn/ui.
  - `hooks/useLiveUpdates.js` — **NEW**: EventSource client subscribing to `/api/live/stream`, auto-reconnect w/ backoff.
  - `pages/CommandCenter.jsx` — invokes `useLiveUpdates` and re-fetches summary/missions/pipeline/top/recent on every push.
- **Env** (all in `/app/backend/.env`): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_ENABLED=true`, `AIRTABLE_OPPORTUNITIES_TABLE=Leads`, `AIRTABLE_LEADS_TABLE=Leads`, `AIRTABLE_LEADS_TABLE_ID=tbliTlH5mmdOjc280`, `AIRTABLE_WEBHOOK_ENABLED=true`, `PUBLIC_BACKEND_URL=https://hound-priorities.preview.emergentagent.com`, `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME=TheShirtlessHandyman`, `EMAIL_REPLY_TO=Theshirtlesshandyman@gmail.com`.

## User Persona
Ryan (contractor operator) — needs to know within 30 seconds what deserves attention today, and every action (approve, send, update) should reflect on the dashboard within a second.

## Implemented
- Command Center, Opportunities list + detail, Today's Missions, Relationships/Intelligence placeholders, Settings, mobile bottom nav.
- ⌘K Command Palette, Editable Decision Panel, Live Refresh Indicator, Priority band + Mission normalizers.
- Next Best Action panel — Approve/Hold/Skip/DNC + draft-message editing.
- Dashboard rewired to Leads table with full derivation of priority score/band, status, daily mission, opportunity fit, momentum, reachability, activity timeline.
- PATCH endpoint hardening — empty/unknown bodies return 200, Airtable errors surface as 4xx (never 500), empty-string clears date fields, `typecast=True`.
- Opportunity Detail hero grid locked to `minmax(0,1fr) 320px` — labels never overlap.
- Approve & Send goes live via Resend — guardrails (missing email, DNC, Rejected, etc.), fallback template with merge tags, Airtable writes on success, lead retained on failure.
- **Airtable Webhooks + Live SSE (2026-02-02, LATEST)**:
  - Backend startup registers a webhook against Leads (`tbliTlH5mmdOjc280`), watching `add` + `update` change types on `tableData`.
  - `/api/airtable/webhook` verifies HMAC-SHA256 signature, spawns a background task, returns 200 immediately.
  - Background task fetches payloads via cursor, invalidates BOTH service caches, broadcasts `{type:'airtable_change', changed_record_ids:[…], at:iso}` to every SSE subscriber.
  - `/api/live/stream` is an SSE endpoint with `ready` + `update` events, 25s heartbeat comments to survive proxies, per-subscriber asyncio.Queue.
  - `/api/live/status` returns webhook registration state (id, table_id, cursor, subscriber count).
  - `/api/live/reregister` rotates the mac secret + webhook id on demand.
  - Frontend `useLiveUpdates` hook auto-reconnects with exponential backoff, invokes a callback on every `update` event.
  - E2E verified: writing to Airtable's `Notes` field triggered `POST /api/airtable/webhook` → signature verified → `GET /webhooks/{id}/payloads?cursor=1 → 200` → caches invalidated → SSE `update` event delivered to the browser → CommandCenter re-fetched all 5 data endpoints.

## P1 Backlog
- **Slack alerts** for Band A opportunities (needs `integration_playbook_expert_v2` + Slack workspace + bot token).
- Twilio/SMS as a second outreach channel once Ryan has a dedicated business number.
- Editable send template + subject line via Settings.
- Persist webhook_id + mac_secret to MongoDB so a preview restart doesn't leave orphaned webhooks (currently re-registers on every startup which is idempotent but wastes a webhook slot).
- Reply tracking (inbound Resend webhook → Airtable `Reply summary`).

## P2 Backlog
- Auth (JWT or Emergent Google Auth).
- Multi-operator team workspaces.
- Surface Raw Signals table on detail page (permit chain).
- Guard `typecast=True` server-side so dashboard status typos can't pollute Airtable options.
- Dedupe airtable_service + leads_service connection code.
- CSV export + weekly digest email.
- Relationship graph MVP.
- Intelligence page: real permit-velocity chart + neighborhood heatmap.

## Known Advisories
- Leads service in-memory skip/hold/approve state diverges under multi-worker uvicorn (single-worker today).
- Webhook mac_secret + cursor + id live in memory — on backend restart the webhook is deleted+re-created (idempotent, no data loss).
- Airtable webhooks last 7 days by default; a 6-day refresh cron isn't wired yet — currently re-registered on every backend restart.
- Preview + production run different backend URLs. The webhook is registered against `PUBLIC_BACKEND_URL` (preview). To make production receive live updates, deploy + set that env var to the production URL then hit `/api/live/reregister`.
- `PUBLIC_BACKEND_URL` **must** be publicly reachable HTTPS or Airtable can't deliver pings.
