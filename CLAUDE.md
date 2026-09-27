# GEAUXleads — CLAUDE.md

## Who runs this project (read first)

Ryan owns this project and makes the final call. **Claude (in Ryan's claude.ai chat) is the
lead/coordinator for GEAUXleads** — it owns the overall plan, the Airtable data layer, and the
Make.com automations, and it decides priorities across the system. Any other AI agent working
in this repo (Claude Code, etc.) works under that direction:

- Stick to the task you were given. Don't take on unrelated refactors, renames, or redesigns.
- **Never** change the Airtable schema (add/rename/delete tables or fields, change select
  options) from the app. Schema changes go through Ryan → lead Claude.
- **Never** delete or merge repos, drop data, or touch Make.com scenarios without Ryan's
  explicit confirmation.
- If something you need is outside your lane, stop and write it up as a request for Ryan to
  bring to the lead Claude.

## What this is

GEAUXleads (formerly "Bloodhound" — some UI and code still uses that name) is Ryan's lead
system for **The Shirtless Handyman**, a New Orleans contractor specializing in premium
microcement and tadelakt surfaces (bathrooms, floors, showers, walls). It finds and ranks
permit projects, partners (designers, remodelers, builders), landlords, investors, and agents,
then helps Ryan decide who to contact and what to say. Airtable is the source of truth; this
repo is the full-stack app on top of it.

Targeting principle: the filter for maintenance/refresh work is **portfolio scale**, not job
title. Small landlords and small property managers are good targets; large operators of either
kind usually have in-house maintenance and are weak targets.

## Tech stack

- **Backend:** FastAPI (Python) in `backend/server.py`, services in `backend/services/`
- **Frontend:** React 18 + react-router-dom, axios, Tailwind-style utility classes with a
  custom theme (CSS vars prefixed `--bh-`, e.g. `--bh-ink`, `--bh-brass`, `--bh-olive`;
  surface class `bh-surface`)
- **Database:** Airtable (live). No local DB. Sample-data fallback exists but production runs
  on the real base.
- **Deploy:** Railway, two services from this repo's `main` branch —
  `geauxleads-frontend-production` (static React build) and `geauxleads-production` (FastAPI).
  Pushes to `main` auto-deploy. **Treat every push to `main` as a production release.**

## Airtable — shared base, many writers

Base: **"Project bloodhounds discovered leads"** (`appuyAHSSzJrPWlec`). This app is NOT the only
thing that writes to it. Make.com scenarios and the lead Claude also read and write here, so
the app must not assume it owns any table or field.

Main tables (read `GET /api/schema` or the base for full field lists):

| Table | What it holds |
| --- | --- |
| Leads | Main dashboard records (permit leads + projections from the registry) |
| Raw Signals | Immutable public permit signals before qualification (formula-scored) |
| Opportunity Registry | Canonical cross-lane opportunities; projects into Leads |
| Decision Desk | Small daily review queue across lanes |
| Partner Intelligence | Designers, remodelers, builders, etc. (evidence-led) |
| Investor Intelligence | LLC/investor owners renovating properties |
| Landlords | Portfolio property owners (e.g. commercial STR license holders) |
| Real Estate Agent Outreach | Pre-listing refresh targets |
| Needs Convincing (Education Pipeline) | Good fits not yet sold on microcement vs. tile |
| Explee Hot Leads | Replies from Explee/AutoGTM outreach — already interested, time-sensitive |
| Instagram / Property Manager Discovery Queue | Unreviewed raw candidates |
| Message Playbooks | Editable draft templates |
| Campaigns / Campaign Recipients / Campaign Events / Suppression List / Contact Profiles | Outreach approval + compliance records |
| AI Decision Log / GEAUXleads Learning Feed | AI recommendation vs. Ryan's actual call, fed back into scoring |
| Properties / Sources / Source Watchlist / Scoring Rules / Review Requests | Supporting data |

Rules for the app:
- Many Leads fields are marked **DEPRECATED** in their Airtable descriptions. Don't build new
  features on them. Some legacy-named fields are still actively written by automations
  (descriptions say "do not delete") — leave those alone.
- **Formula fields** (scores, draft links, value displays) are computed in Airtable. Read them;
  never try to write them or re-implement them in code.
- **Suppression List is absolute.** Anything that drafts or opens a message must respect it.
- Some field descriptions still say "Emergent app." That's stale — the app is this repo now.

## Outreach policy (non-negotiable)

Nothing in GEAUXleads sends messages automatically. The app may generate drafts and open
draft links (SMS/email/iPhone Messages); Ryan sends manually. `Outreach Gate` fields,
Campaign approval, and the Suppression List all have to pass.
- Frontend gate: `outreachAllowed(opp)` in `frontend/src/lib/queue.js` — the single global gate
  for all messaging/draft controls.
- Backend mirror: `backend/services/outreach_policy.py`. Keep both in sync.
- Exception by design: **Explee Hot Leads** are people who already replied. They need fast human
  follow-up and should be highly visible, but the app still doesn't send anything itself.

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
    outreach_policy.py   # backend mirror of the outreach gate
    ... (aggregations, dedupe, audit, etc.)
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
| --- | --- | --- |
| `/` | CommandCenter.jsx | Home dashboard: morning brief, follow-ups, pipeline |
| `/opportunities` | Opportunities.jsx | Project list w/ filters (Lane, Source, Status, Priority, Mission, Type, min score, search) |
| `/opportunities/:id` | OpportunityDetail.jsx | Project detail, drafts, activity |
| `/missions` | Missions.jsx | Today's outreach missions grouped by action |
| `/relationships` | Relationships.jsx | Partner intelligence cards |
| `/intelligence` | Intelligence.jsx | Projects to watch |
| `/discovery/*` | Discovery*.jsx | Permit/landlord/property-manager discovery (not in sidebar) |
| `/debug` | DebugPanel.jsx | Diagnostics (not in sidebar) |
| `/settings` | Settings.jsx | Data sources, message playbooks, config |

Nav labels live in `frontend/src/components/Sidebar.jsx`. The `/` route is labeled **"Home"**
(do not rename to "Command Center" — that was a regression, reverted by Ryan's request).

## Backend API (all under `/api`)

- `GET /health`, `GET /config` — health + Airtable wiring status
- `GET /opportunities` — list w/ filters: `source status priority_band daily_mission project_type lane min_score q sort` (sort=`lead_score` default)
- `GET /opportunities/summary|/missions|/pipeline|/recent|/top|/lanes|/top-by-lane|/duplicates`
- `GET|PATCH /opportunities/{id}[/status|/mission|/fields]`, `POST .../result`, `POST .../activity`
- `GET /message-playbooks`, `PATCH /message-playbooks/{id}`
- `GET /drafts[/queue]`, `POST /drafts`
- `GET /leads/next-best-action`, `GET /leads/{id}/eligibility|/readiness`, `POST /leads/{id}/action`
- `POST /cache-refresh`, `GET /cache-status`, `GET /schema`

## Key domain concepts

- **Opportunity** = one Airtable row as normalized by the backend. Core fields: `name`, `status`,
  `lane` (`market_capture`|`partner`|`non_permit`), `priority_band` (A/B/C/D), `priority_score`
  (0–100), `daily_mission` ("Call Today"|"Send Text"|"Send Email"|"Research First"|
  "Visit Property"|"Prepare Estimate"|"Ask for Referral"|"Follow Up"|"Wait"), `current_queue`,
  `contact_state`, `estimated_value`, `source`.
- **Priority display:** UI shows plain English (High/Medium/Low) via `priorityLevel()` in
  `lib/priority.js`; raw scores stay in `title=` hover.
- **Money display:** `moneyDisplay(opp)` / `fmtMoneyOrStatus(v, label)` in `lib/formatters.js` —
  the single renderers. **Never invent values**; show "Not public" / "Not estimated yet".

## Environment variables

Backend (Railway): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_OPPORTUNITIES_TABLE`
(= `${{shared.AIRTABLE_OPPORTUNITIES}}` service reference — Railway can't rename shared vars),
`AIRTABLE_ENABLED=true`.
Frontend build: `REACT_APP_BACKEND_URL` (baked at build time).
Never commit keys. Never log the API key.

## Open tasks (do these, then delete the line)

1. Add a React error boundary around each route so one throwing component can't blank the page.
2. Add `.catch` to `api.listOpportunities().then(setItems)` in Opportunities.jsx and show a real
   error state instead of "No opportunities match your filters."
3. Add a render smoke test that loads each route against real API data and fails on
   ReferenceError (catches the dropped-import problem below).
4. Surface **Explee Hot Leads** (unreviewed, newest first) prominently on Home.

## Gotchas (learned the hard way)

- A corrupt merge (Sep 2026) silently dropped import identifiers, e.g. `fmtMoneyOrStatus` was
  used but not imported in OpportunityRow.jsx and OpportunityDetail.jsx — every row threw
  ReferenceError and blanked the page. After any merge, check that identifiers used from
  `@/lib/*` are actually imported.
- Discovery/Debug routes exist but are intentionally not in the sidebar.
- `bloodhound-opportunity-intel` repo was deleted; the two repos are `GEAUXleads` and
  `the-shirtless-handyman`. Never delete/merge repos without explicit confirmation from Ryan.

## Common tasks

- Run backend locally: `cd backend && uvicorn server:app --reload` (needs the four Airtable env vars).
- Frontend dev: `cd frontend && npm start` with `REACT_APP_BACKEND_URL` pointing at the Railway
  backend or local server.
- Verify production: `GET /api/health` should show `{"ok":true, "backend":"airtable","count":N}`;
  `GET /api/config` shows wiring status.

## Definition of done for any change

Builds cleanly, every route renders against real data, the outreach gate is untouched (or
changed in both frontend and backend), no schema writes, and a one-paragraph summary of what
changed for Ryan to pass back to the lead Claude.
