# GEAUXleads — CLAUDE.md

## What this is
GEAUXleads (branded "Bloodhound" in the UI) is Ryan's lead-tracking CRM for his
handyman business, The Shirtless Handyman. It tracks permit projects, partner
relationships, and outreach missions — what's worth pursuing, who to contact,
and what to do next. Data lives in Airtable; this repo is the full-stack app.

## Tech stack
- **Backend:** FastAPI (Python) in `backend/server.py`, services in `backend/services/`
- **Frontend:** React 18 + react-router-dom, axios, Tailwind-style utility classes
  with a custom "Bloodhound" theme (CSS vars prefixed `--bh-`, e.g.
  `--bh-ink`, `--bh-brass`, `--bh-olive`; surface class `bh-surface`)
- **Database:** Airtable (live). No local DB. Sample-data fallback exists but
  production runs on the real base.
- **Deploy:** Railway, two services from this repo's `main` branch —
  `geauxleads-frontend-production` (static React build) and
  `geauxleads-production` (FastAPI). Pushes to `main` auto-deploy.

## Repo layout
```
backend/
  server.py              # all API routes (api_router, mounted under /api)
  services/
    airtable_service.py  # Airtable I/O, sort/filter logic (sort_opportunities)
    opportunity_service.py
    leads_service.py
    discovery_service.py # permit/landlord discovery
    draft_service.py     # outreach message drafts
    playbook_service.py  # message playbook templates
    morning_brief_service.py
    ... (aggregations, dedupe, audit, outreach_policy, etc.)
  requirements.txt
  tests/
frontend/
  src/
    pages/               # route components (see below)
    components/          # shared UI (badges, rows, drawers, dialogs)
    lib/
      api.js             # axios client; BASE = REACT_APP_BACKEND_URL + /api
      formatters.js      # money/date/source display helpers
      constants.js       # MISSIONS, STATUSES, BANDS, LANES, SOURCES, ...
      priority.js        # priorityLevel / contactState / contactReady logic
      queue.js           # outreachAllowed() — the global outreach gate
    hooks/ layouts/ constants/
```

## Frontend pages (routes)
| Route | File | Purpose |
|---|---|---|
| `/` | CommandCenter.jsx | Home dashboard: morning brief, follow-ups, pipeline |
| `/opportunities` | Opportunities.jsx | Project list w/ filters (Lane, Source, Status, Priority, Mission, Type, min score, search) |
| `/opportunities/:id` | OpportunityDetail.jsx | Project detail, drafts, activity |
| `/missions` | Missions.jsx | Today's outreach missions grouped by action |
| `/relationships` | Relationships.jsx | Partner intelligence cards |
| `/intelligence` | Intelligence.jsx | Projects to watch |
| `/discovery/*` | Discovery*.jsx | Permit/landlord/property-manager discovery (not in sidebar) |
| `/debug` | DebugPanel.jsx | Diagnostics (not in sidebar) |
| `/settings` | Settings.jsx | Data sources, message playbooks, config |

Nav labels live in `frontend/src/components/Sidebar.jsx`. The `/` route is
labeled **"Home"** (do not rename to "Command Center" — that was a rebrand
regression, reverted by user request).

## Backend API (all under `/api`)
- `GET /health`, `GET /config` — health + Airtable wiring status
- `GET /opportunities` — list w/ filters: `source status priority_band
  daily_mission project_type lane min_score q sort` (sort=`lead_score` default)
- `GET /opportunities/summary|/missions|/pipeline|/recent|/top|/lanes|/top-by-lane|/duplicates`
- `GET|PATCH /opportunities/{id}[/status|/mission|/fields]`, `POST .../result`, `POST .../activity`
- `GET /message-playbooks`, `PATCH /message-playbooks/{id}`
- `GET /drafts[/queue]`, `POST /drafts`
- `GET /leads/next-best-action`, `GET /leads/{id}/eligibility|/readiness`, `POST /leads/{id}/action`
- `POST /cache-refresh`, `GET /cache-status`, `GET /schema`

## Key domain concepts
- **Opportunity** = one Airtable row. Core fields: `name`, `status`, `lane`
  (`market_capture`|`partner`|`non_permit`), `priority_band` (A/B/C/D),
  `priority_score` (0–100), `daily_mission` ("Call Today"|"Send Text"|
  "Send Email"|"Research First"|"Visit Property"|"Prepare Estimate"|
  "Ask for Referral"|"Follow Up"|"Wait"), `current_queue`, `contact_state`,
  `estimated_value`, `source`.
- **Outreach gate:** `outreachAllowed(opp)` in `frontend/src/lib/queue.js` is
  the single global gate for all messaging/draft controls. Backend mirror:
  `backend/services/outreach_policy.py`.
- **Priority display:** UI shows plain English (High/Medium/Low) via
  `priorityLevel()` in `lib/priority.js`; raw scores stay in `title=` hover.
- **Money display:** `moneyDisplay(opp)` / `fmtMoneyOrStatus(v, label)` in
  `lib/formatters.js` — the single renderers; never invent values.

## Environment variables
Backend (Railway): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`,
`AIRTABLE_OPPORTUNITIES_TABLE` (= `${{shared.AIRTABLE_OPPORTUNITIES}}` service
reference — Railway can't rename shared vars), `AIRTABLE_ENABLED=true`.
Frontend build: `REACT_APP_BACKEND_URL` (baked at build time).

## Gotchas (learned the hard way)
- A corrupt merge (Sep 2026) silently dropped import identifiers, e.g.
  `fmtMoneyOrStatus` was used but not imported in OpportunityRow.jsx and
  OpportunityDetail.jsx — every row threw ReferenceError and blanked the page.
  After any merge, sanity-check that identifiers used from `@/lib/*` are
  actually imported (a render test against real API data catches this fast).
- The frontend has no error boundaries: one throwing component blanks the
  whole route.
- `api.listOpportunities().then(setItems)` in Opportunities.jsx has no
  `.catch` — a failed fetch silently shows "No opportunities match your filters."
- Discovery/Debug routes exist but are intentionally not in the sidebar.
- `bloodhound-opportunity-intel` repo was deleted; the two repos are
  `GEAUXleads` and `the-shirtless-handyman`. Never delete/merge repos without
  explicit user confirmation.

## Common tasks
- Run backend locally: `cd backend && uvicorn server:app --reload` (needs the
  four Airtable env vars).
- Frontend dev: `cd frontend && npm start` with `REACT_APP_BACKEND_URL`
  pointing at the Railway backend or local server.
- Verify production: `GET /api/health` should show `{"ok":true,
  "backend":"airtable","count":N}`; `GET /api/config` shows wiring status.
