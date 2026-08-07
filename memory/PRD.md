# BLOODHOUND: AI Opportunity Intelligence — PRD

## Original problem statement
Build a premium full-stack app for The Shirtless Handyman (Ryan Mena) that
discovers, understands, and prioritizes business opportunities, partners,
and market signals from an Airtable base. **All outreach is native-only** —
`sms:` and `mailto:` URLs. Nothing sends automatically; Ryan always presses
Send on his own Apple device.

## Users
- **Ryan** (Account Lead) — owner-operator contractor, uses iPhone + laptop.

## Core requirements (unchanged)
- Airtable is the source of truth (Leads table).
- Real-time updates via Airtable webhook → backend SSE → frontend refetch.
- No automated sending. No Resend, no Twilio, no Gmail API, no messaging
  provider, no Apple account integration.
- All outreach flows through `sms:` and `mailto:` links only.
- Approval-only. Nothing sends from any screen.

## Tech stack
- Frontend: React 18 + Tailwind + Shadcn/UI
- Backend: FastAPI + PyAirtable + Motor (MongoDB)
- Data: Airtable (leads, playbooks) + MongoDB (drafts, handoff log, user settings)

## Implemented (2026 session log)
- ✅ Command Center dashboard (Today's Work, metrics, follow-ups, top picks, pipeline)
- ✅ Airtable read-through with SSE live updates
- ✅ Slack alerting for Band-A leads
- ✅ Draft a Note drawer + Playbook editor
- ✅ Review Queue (renamed "Needs a Look")
- ✅ Native iPhone handoff via `sms:` / `mailto:` (OpenInMessages.jsx)
- ✅ Row-level Text/Email pills on People to Know + Projects to Watch
- ✅ Handoff logger — every tap logs one event to Mongo `contact_handoffs`
- ✅ **UX/wording rewrite** — plain English throughout (see below)
- ✅ **Sender email in Settings** — MongoDB-backed user preference; injected
     into every `mailto:` body so Ryan sees the right From address
- ✅ Removed leftover "Approve & Send" button from Today's top action
- ✅ Priority displayed as **High / Medium / Low** (numeric score hidden behind hover)
- ✅ Contact readiness badge — green / yellow / gray / red

## Plain-English terminology map (applied everywhere Ryan sees it)
| Old / technical         | New / plain-English            |
|-------------------------|--------------------------------|
| Partner Intelligence    | People to Know                 |
| Project Signals         | Projects to Watch              |
| Signal Source           | Found on                       |
| Contact confidence      | Can I reach them?              |
| Review Queue            | Needs a Look                   |
| Recommended Next Move   | What to do next                |
| Daily Mission           | Today's action                 |
| Lead score              | Priority                       |
| Opportunity Registry    | Project List                   |
| Research first          | Get more info first            |
| Pipeline value          | Possible work value            |
| Approve & Send          | (removed entirely)             |

## API surface (new/relevant)
- `GET  /api/settings/user` — get sender identity + prefs
- `PATCH /api/settings/user` — update sender_email / sender_name (validated)
- `POST /api/opportunities/{id}/handoff` — log a Text/Email tap
- `GET  /api/opportunities/{id}/handoffs` — recent handoffs for one lead
- `GET  /api/handoffs/recent` — global recent handoffs

## Data models (Mongo)
- `outreach_drafts` — Draft-a-Note storage
- `contact_handoffs` — one row per Text/Email tap (opp_id, channel, recipient, device_hint, at)
- `user_settings` — singleton doc: `{ sender_email, sender_name, updated_at }`

## Backlog / Next
- P1 · Persist the Airtable webhook manager state to Mongo so preview
       reloads don't hijack production's webhook.
- P2 · Consolidate remaining "Section /XX" numbering across
       Opportunities.jsx and OpportunityDetail.jsx (mostly done).
- P2 · Add a "Handoffs today" strip on the Command Center so Ryan can see
       what he's already texted/emailed without leaving the dashboard.
- P3 · Offer more built-in sender identities (business vs personal email)
       if Ryan wants a one-tap toggle instead of editing Settings.
