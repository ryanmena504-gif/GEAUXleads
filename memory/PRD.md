# Bloodhound — PRD

## Original Problem Statement
Build a premium full-stack web application called BLOODHOUND — AI Opportunity Intelligence for contractors. Command Center that helps discover, understand, and prioritize business opportunities before competitors. Dark, high-end, Palantir/Linear aesthetic with amber/gold accents. Reads live from Airtable and allows approved-field writes back.

## Architecture
- **Backend**: FastAPI at `/api`. Two service layers, both live against a single Airtable base:
  - `services/airtable_service.py` — projects the **`Leads`** Airtable table into the dashboard's Opportunity DTO. (Perplexity rebuilt Ryan's Make scenarios and dropped the original `Opportunities` table; Leads is now the source of truth.) 45s TTL cache with auto-retry. `AirtableWriteError` translates Airtable 4xx into FastAPI HTTPExceptions.
  - `services/leads_service.py` — same Leads table, read from a different angle for the Next Best Action panel (per-session skip/hold/approve state, strict write-allowlist).
- **Frontend**: React + Tailwind + shadcn/ui. Dark charcoal (#0B0C10) with amber (#D97706) accents.
- **Env**: `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_ENABLED=true`, `AIRTABLE_OPPORTUNITIES_TABLE=Leads`, `AIRTABLE_LEADS_TABLE=Leads`.

## User Persona
Ryan (contractor operator) — needs to know within 30 seconds "what deserves my attention today" and "is this opportunity worth pursuing, and what should I do next".

## Implemented
- Command Center, Opportunities list + detail, Today's Missions, Relationships/Intelligence placeholders, Settings, mobile bottom nav.
- ⌘K Command Palette, Editable Decision Panel, Live Refresh Indicator, Priority band + Mission normalizers.
- **Next Best Action panel** — reads Leads. Approve/Hold/Skip/Do Not Contact + draft-message editing. Data-quality gate excludes skeleton rows.
- **Dashboard rewired to Leads table (2026-02-02)**:
  - Full field map + derivation for `priority_score` (synthesised from richness signals), `priority_band` (A/B/C/D), `status` (checkbox funnel), `daily_mission` (keyword-normalised), `opportunity_fit`, `momentum`, `reachability`, `activity_timeline` (real timestamps only).
  - Write-allowlist: `Status`, `Hunt status`, `Next followup`, `Rejection reason`, `Notes`, `Approval status`, `Outreach status`. Uses `typecast=True` to auto-add missing single-select options.
  - PATCH endpoint returns 200 on empty/unknown-only bodies (silent-ignore), 4xx on Airtable errors (never 500), and supports empty-string clears for date/select fields.
- **Opportunity Detail hero grid (2026-02-02)** — CSS-grid template locked to `minmax(0,1fr) 320px` so meta labels (Priority/Est. value/Source/Project type) never squeeze/overlap on desktop.

## P1 Backlog
- **Slack alerts** for Band A opportunities (needs `integration_playbook_expert_v2` + Slack workspace + bot token).
- **Airtable webhooks** — blocked on adding `webhook:manage` scope to Ryan's PAT.
- Real outbound messaging behind Approve & Send.
- Relationship graph MVP.
- Intelligence page: real permit-velocity chart + neighborhood heatmap.

## P2 Backlog
- Auth (JWT or Emergent Google Auth).
- Multi-operator team workspaces.
- Surface Raw Signals table on detail page (permit chain).
- Dedupe airtable_service + leads_service connection code.
- CSV export + weekly digest email.
- Guard `typecast=True` server-side so dashboard status typos can't pollute Airtable options.

## Known Advisories
- `typecast=True` auto-adds new single-select options if the dashboard sends a value Airtable doesn't have — great for freeform values, risky for typos. Consider a server-side allowlist.
- Priority is currently synthesised (no live Lead score in Airtable). When Ryan's automation starts populating `Lead score`, it takes over.
- Live lead count fluctuates as automation adds/removes rows (currently 92, was 113 during initial rewire).
