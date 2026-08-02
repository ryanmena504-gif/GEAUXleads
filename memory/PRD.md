# Bloodhound — PRD

## Original Problem Statement
Build a premium full-stack web application called BLOODHOUND — AI Opportunity Intelligence for contractors. Command Center that helps discover, understand, and prioritize business opportunities before competitors. Dark, high-end, Palantir/Linear aesthetic with amber/gold accents. Reads live from Airtable and allows approved-field writes back. Approve & Send actually delivers outbound email through the Emergent-managed Resend integration.

## Architecture
- **Backend**: FastAPI at `/api`. Three service layers, all against the same Airtable base:
  - `services/airtable_service.py` — projects the live `Leads` table into the Opportunity DTO the dashboard speaks (Opportunities table no longer exists; Perplexity rebuilt the Make scenarios and dropped it). 45s TTL cache, `typecast=True` writes, `AirtableWriteError` for graceful 4xx propagation.
  - `services/leads_service.py` — same Leads table, NBA queue with session-level skip/hold/approve state, strict write-allowlist. Now includes `can_send()` guardrails, `compose_email()` template fill, `mark_sent()` for post-send Airtable state.
  - `services/email_service.py` — Emergent-managed Resend proxy; `send_outreach_email()` async, `X-Email-Key` header, raises `EmailSendError` with upstream status code.
- **Frontend**: React + Tailwind + shadcn/ui. Dark charcoal (#0B0C10) with amber (#D97706) accents.
- **Env** (all in `/app/backend/.env`): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_ENABLED=true`, `AIRTABLE_OPPORTUNITIES_TABLE=Leads`, `AIRTABLE_LEADS_TABLE=Leads`, `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME=TheShirtlessHandyman`, `EMAIL_REPLY_TO=Theshirtlesshandyman@gmail.com`.

## User Persona
Ryan (contractor operator) — needs to know within 30 seconds what deserves attention today and, when he clicks Approve, the message actually goes out.

## Implemented
- Command Center, Opportunities list + detail, Today's Missions, Relationships/Intelligence placeholders, Settings, mobile bottom nav.
- ⌘K Command Palette, Editable Decision Panel, Live Refresh Indicator, Priority band + Mission normalizers.
- **Next Best Action panel** with Approve/Hold/Skip/DNC + draft-message editing.
- **Dashboard rewired to Leads table** with full field map + derivations (priority score/band, status, daily mission, opportunity fit, momentum, reachability, activity timeline).
- **PATCH endpoint hardening** — empty/unknown-only bodies return 200, Airtable errors surface as proper 4xx, empty-string clears date fields, `typecast=True`.
- **Opportunity Detail hero grid** locked to `minmax(0,1fr) 320px` so meta labels never overlap.
- **Approve & Send goes live via Resend (2026-02-02)**:
  - Sender display name = TheShirtlessHandyman, reply-to = Theshirtlesshandyman@gmail.com.
  - Uses lead's AI-drafted `First message` when present, else a permit-referencing fallback template with merge tags (`first_name`, `opportunity_type`, `project_address`).
  - **Guardrails**: refuses to send if the lead has no `Contact email`, if `Status` contains "Do not contact", if `Hunt status` contains "Rejected"/"Closed"/"Disqualified", or if `Outreach status` contains "reject". All return HTTP 422 with a clear reason.
  - **On success**: Airtable `Outreach sent`=true, `Message sent date`=now (ISO UTC), `Outreach channel`="Email", `Approval status`="Approved", `Outreach status`="Sent". If the fallback template was used, the composed body is persisted to `First message` so Ryan can see exactly what went out.
  - **On failure**: lead stays in the approval queue — no fields mutated, provider error surfaced as 4xx/5xx.
  - `POST /api/admin/reload` now resets BOTH opportunity + leads service singletons.
  - E2E verified against real Resend proxy (delivered@resend.dev): 12/13 auto tests green + 1 hotfix (missing Hunt status field mapping) applied and manually re-verified.

## P1 Backlog
- **Airtable webhooks** — blocked on adding `webhook:manage` scope to Ryan's PAT.
- **Slack alerts** for Band A opportunities.
- Add Twilio/SMS as a second outreach channel once Ryan has a dedicated business number.
- Editable send template + subject line via Settings (currently baked into `_FALLBACK_TEXT`).
- Relationship graph MVP.
- Intelligence page: permit-velocity chart + neighborhood heatmap.

## P2 Backlog
- Auth (JWT or Emergent Google Auth).
- Multi-operator team workspaces.
- Surface Raw Signals table on detail page (permit chain).
- Guard `typecast=True` server-side so dashboard status typos can't pollute Airtable options.
- Dedupe airtable_service + leads_service connection code.
- CSV export + weekly digest email.
- Reply tracking (inbound Resend webhook → Airtable `Reply received`/`Reply summary`).

## Known Advisories
- Leads service in-memory skip/hold/approve state diverges under multi-worker uvicorn (single-worker today).
- `typecast=True` auto-adds new single-select options — great for freeform values, risky for typos.
- Priority is synthesised until Ryan's automation populates `Lead score`.
- Live lead count fluctuates as the automation adds/removes rows (currently ~92).
- If EMERGENT_EMAIL_KEY is ever revoked, /api/leads/{id}/action approve returns 503 with a clear reason (never 500).
