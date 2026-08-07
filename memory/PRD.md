# BLOODHOUND: AI Opportunity Intelligence — PRD

## Original problem statement
Premium full-stack app for The Shirtless Handyman (Ryan Mena) that discovers,
understands, and prioritizes business opportunities, partners, and market
signals from an Airtable base. **All outreach is native-only** — `sms:` and
`mailto:` URLs. Nothing sends automatically; Ryan always presses Send on his
own Apple device.

## User
- **Ryan Mena** — owner-operator contractor. iPhone + Mac. Fixed sender identity:
  ryanmena@theshirtlesshandyman.com · (504) 264-4919.

## Core rules
- Airtable Leads table is the source of truth.
- Live via webhook → SSE → frontend refetch.
- No provider sending. No Resend/Twilio/Gmail/iMessage APIs. No Apple account
  integration. Approval-only, always.
- Every outreach flows through `<a href="sms:...">` or `<a href="mailto:...">`.

## Tech stack
- Frontend: React 18 + Tailwind + Shadcn/UI + Motion for React
- Backend: FastAPI + PyAirtable + Motor (MongoDB)
- Data: Airtable (leads, playbooks) + MongoDB (drafts, handoffs, user_settings)

## Session log — implemented
### Foundation
- Command Center dashboard (Today's Work + metric strip + lanes + follow-ups + top picks + pipeline)
- Airtable read-through with SSE live updates
- Slack alerts for high-priority leads
- Draft-a-Note drawer + Playbook editor
- Review queue

### Native handoff
- `sms:` / `mailto:` URLs only. iPhone-safe phone sanitization.
- Handoff logger — every Text/Email tap logs one row to Mongo `contact_handoffs`
- Row-level Text/Email pills on People to Know + Projects to Watch
- Removed the leftover "Approve & Send" button entirely
- iPhone hint under every panel: "Open Bloodhound on your iPhone to text from your phone."

### Sender identity (fixed for Ryan)
- Mongo-backed singleton `user_settings` (`sender_email` / `sender_name` / `sender_phone`)
- Settings → "Your sender identity" with three inputs, seeded with Ryan's real values
- Signature auto-added to every mailto: body: `Ryan Mena` · `The Shirtless Handyman` · `(504) 264-4919` · `ryanmena@theshirtlesshandyman.com`

### Plain-English UX pass (this session)
| Old (technical / marketing)       | New (contractor English)              |
|-----------------------------------|---------------------------------------|
| Partner Intelligence              | People to Know                        |
| Project Signals                   | Projects to Watch                     |
| Signal Source                     | Found on                              |
| Contact confidence                | Can I reach them?                     |
| Review Queue                      | Needs a Look                          |
| Recommended Next Move             | What to do next                       |
| Daily Mission                     | Today's action                        |
| Lead score                        | Priority                              |
| Opportunity Registry              | Project List                          |
| Research first                    | Get more info first                   |
| Approval gate                     | Ready for your approval               |
| Pipeline value                    | Possible work value                   |
| Approve & Send                    | (removed entirely)                    |
| Intelligence (section)            | Why this project matters              |
| Contact (section)                 | Who to talk to                        |
| Property & Project                | The project                           |
| Activity Timeline                 | Recent activity                       |
| Missing information               | Still need to know                    |
| Risk flags                        | Watch out for                         |
| Evidence summary                  | What we found                         |
| Section / 01 (etc.)               | (dropped — sections have real titles) |
| Mock Relationships preview        | (removed)                             |

### Modernization
- Priority is displayed as **High / Medium / Low** with numeric score only in hover.
- Contact readiness badge (green/yellow/gray/red) shown on every lead.
- Status badge maps `Needs research` → **Need more info**, `Disqualified` → **Not a fit**, etc.
- Lane names swapped to plain English (Projects · People to Know · Watching).
- Command palette rebuilt with new plain-English labels.
- Empty states and helper copy all rewritten.

## Data models (Mongo)
- `outreach_drafts` — Draft-a-Note storage
- `contact_handoffs` — {opp_id, channel, recipient, device_hint, at}
- `user_settings` — singleton {sender_email, sender_name, sender_phone, updated_at}

## API surface
- `GET  /api/settings/user` · `PATCH /api/settings/user`
- `POST /api/opportunities/{id}/handoff` · `GET /api/opportunities/{id}/handoffs`
- `GET  /api/handoffs/recent`
- (+ existing opportunities / drafts / playbook / lane / pipeline endpoints)

## Backlog / Next
- **Handoffs Today Strip** on Today's Work
- **Signature preview** in Settings
- **Sender email presets** (business vs personal one-tap toggle)
- **Webhook persistence** to Mongo so preview reloads don't hijack production
- **Per-lead sender note** (drop business tagline for one specific reply)
