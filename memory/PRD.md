# Bloodhound — PRD

## Original Problem Statement
Build a premium full-stack web application called BLOODHOUND — AI Opportunity Intelligence for contractors. Command Center that helps discover, understand, and prioritize business opportunities before competitors. Dark, high-end, Palantir/Linear aesthetic with amber/gold accents. Reads live from Airtable and allows approved-field writes back.

## Architecture
- **Backend**: FastAPI at `/api`. Two service layers, both live against a single Airtable base:
  - `services/airtable_service.py` — projects the **`Leads`** Airtable table into the dashboard's Opportunity DTO. (The original `Opportunities` table was dropped when Perplexity rebuilt Ryan's Make scenarios; Leads is now the source of truth.) 45s TTL cache with auto-retry.
  - `services/leads_service.py` — same Leads table, read from a different angle for the Next Best Action panel (per-session skip/hold/approve state, strict write-allowlist).
- **Frontend**: React + Tailwind + shadcn/ui. Dark charcoal (#0B0C10) with amber (#D97706) accents.
- **Env**: `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_ENABLED=true`, `AIRTABLE_OPPORTUNITIES_TABLE=Leads`, `AIRTABLE_LEADS_TABLE=Leads` — all in `/app/backend/.env`.

## User Persona
Ryan (contractor operator) — needs to know within 30 seconds "what deserves my attention today" and "is this opportunity worth pursuing, and what should I do next".

## Implemented
### 2026-02 initial build
- Command Center, Opportunities list + detail, Today's Missions, Relationships/Intelligence placeholders, Settings, mobile bottom nav.

### 2026-02 live Airtable + polish
- Live Airtable via `pyairtable` with write-allowlist and 45s cache w/ auto-retry.
- ⌘K Command Palette, Editable Decision Panel, Live Refresh Indicator.
- Priority band + Mission normalizers matching Ryan's SWITCH formula.

### 2026-02 Next Best Action panel
- Hero panel on Command Center reading Leads. Approve, Hold, Skip, Do Not Contact, draft-message editing. 404 on missing ids. Data-quality gate (excludes skeleton rows).

### 2026-02 Dashboard rewired to Leads (LATEST)
- The core `airtable_service.py` no longer looks for an "Opportunities" table (it doesn't exist in the base). It now projects the **80-column Leads table** into the Opportunity DTO the frontend already speaks.
- **Field map**: identity, timestamps, signal, contact block, AI intelligence, workflow state, dates, funnel checkboxes, money — all mapped from Leads columns to snake_case keys.
- **Derived values**:
  - `priority_score` — synthesised from richness signals (Ai status Complete, contact fields, permit, estimated value, verified/qualified/premium/partnership flags) until Airtable starts scoring.
  - `priority_band` — A/B/C/D from score, honouring explicit `Priority` when set.
  - `status` — derived from checkbox funnel (Job won → Won, Estimate → Estimate sent, Reply → Conversation started, Outreach sent → Estimate requested, Approval status Approved → Ready, Enrichment status Needs research → Needs research, else raw `Status` or "New").
  - `daily_mission` — keyword-normalised from `Next action`/`recommended action`/`Outreach angle`/`Best contact method`.
  - `opportunity_fit`, `momentum`, `reachability` — qualitative labels derived from Revenue potential, Recent activity flag, and contact fields.
  - `activity_timeline` — real timestamps only (discovered / validated / message generated / message sent / reply / status change).
- **Write allowlist**: `Status`, `Hunt status` (from Ryan's decision), `Next followup`, `Rejection reason` (from outcome), `Notes`, `Approval status`, `Outreach status`. Everything else read-only.
- Dashboard verified against real base: 113 leads, 79 scored, pipeline populated (40 New / 72 Needs research / 1 Ready), missions grouped (71 Research First / 5 Send Email / 5 Prepare Estimate / 32 Wait).

## P1 Backlog
- **Slack alerts** for Band A opportunities (needs `integration_playbook_expert_v2` + Slack workspace + bot token).
- **Airtable webhooks** — blocked on adding `webhook:manage` scope to Ryan's PAT (user was walked through the UI steps but hasn't confirmed yet).
- Real outbound messaging behind Approve & Send.
- Relationship graph MVP (nodes: past clients, subs, mutuals).
- Intelligence page: real permit-velocity chart + neighborhood heatmap.

## P2 Backlog
- Auth (JWT or Emergent Google Auth).
- Multi-operator team workspaces.
- Dedicated Interactions/Activities table.
- Dedupe airtable_service + leads_service connection code.
- CSV export + weekly digest email.
- Surface Raw Signals table on detail page (permit chain).

## Known Advisories
- `leads_service` per-process skip/hold sets diverge under multi-worker uvicorn (single-worker today).
- `do_not_contact` silently falls back to session-only if Airtable single-select lacks the option.
- Priority is currently synthesised (no live Lead score in Airtable). When Ryan's automation starts populating `Lead score`, it takes over.
