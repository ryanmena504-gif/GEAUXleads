# BLOODHOUND: AI Opportunity Intelligence — PRD

## Original problem statement
Premium full-stack app for The Shirtless Handyman (Ryan Mena) that discovers,
understands, and prioritizes business opportunities, partners, and market
signals from an Airtable base. **All outreach is native-only** — `sms:`,
`mailto:`, and provider compose URLs (Gmail/Outlook Web). Nothing sends
automatically; Ryan always presses Send himself.

## User
- **Ryan Mena** — owner-operator contractor. iPhone + Mac. Fixed sender identity:
  ryanmena@theshirtlesshandyman.com · (504) 264-4919 · Gmail (Google Workspace).

## Core rules
- Airtable Leads table is the source of truth.
- Live via webhook → SSE → frontend refetch.
- No provider sending. No Resend/Twilio/Gmail API/iMessage APIs. No Apple
  account integration. Approval-only, always.
- Every outreach flows through a plain `sms:`, `mailto:`, or provider
  compose URL (Gmail authuser= or Outlook deeplink).

## Tech stack
- Frontend: React 18 + Tailwind + Shadcn/UI
- Backend: FastAPI + PyAirtable + Motor (MongoDB)
- Data: Airtable (leads, playbooks) + MongoDB (drafts, handoffs, user_settings)

## Implemented (major features)
### Discovery + prioritisation
- Command Center dashboard with Won-this-month KPI hero, Today's top action,
  Time to nudge, metric strip, follow-ups, top picks, pipeline
- Airtable read-through with SSE live updates
- Slack alerts for high-priority leads
- Priority as High/Medium/Low pill (score hidden behind hover)
- Contact readiness badge (green/yellow/gray/red) on every lead

### Outreach — native + provider-locked
- `sms:` / `mailto:` URLs with iPhone-safe phone sanitization
- **Email provider lock** — Gmail compose URL with `authuser=` param forces
  every email to send from Ryan's business account on every device
- Configurable in Settings → Your sender identity (Name / Email / Phone / Provider)
- Handoff logger — every Text/Email tap logs one row to Mongo `contact_handoffs`
- Row-level Text/Email pills on People to Know + Projects to Watch
- Removed leftover "Approve & Send" button

### Follow-up sequencing (2026-08 session)
- `GET /api/follow-ups/due` — joins handoff_log with opportunity list to
  surface leads Ryan touched but never nudged, bucketed by:
    · estimate_check (7+ days since Estimate requested/sent)
    · text_nudge     (3+ days since last text)
    · email_nudge    (5+ days since last email)
- Ranked estimate → text → email, then by priority score, then by days idle
- Time to nudge section on Today's Work shows top 8 with one-tap Contact them

### Business trend at a glance (2026-08 session)
- `GET /api/kpis/monthly` — Won this month, Active pipeline, Estimates out,
  Won all-time (count + value each)
- WonThisMonth hero strip at the very top of Today's Work

### Plain-English UX
- Full rebrand (Partner Intelligence → People to Know, Lead score → Priority,
  Pipeline value → Possible work value, Research First → Get more info first,
  etc.)
- Status labels ("Need more info", "Talking", "Not a fit")
- Section /XX numbering removed; sections have real titles

## Data models (Mongo)
- `outreach_drafts` — Draft-a-Note storage
- `contact_handoffs` — {opp_id, channel, recipient, device_hint, at}
- `user_settings` — {sender_email, sender_name, sender_phone, email_provider, updated_at}

## API surface (relevant/new)
- `GET  /api/follow-ups/due` — leads needing a nudge
- `GET  /api/kpis/monthly` — Won this month + pipeline value
- `GET  /api/settings/user` · `PATCH /api/settings/user`
- `POST /api/opportunities/{id}/handoff` · `GET /api/opportunities/{id}/handoffs`
- `GET  /api/handoffs/recent`
- (+ existing opportunities / drafts / playbook / lane / pipeline endpoints)

## Backlog / Next
- **Signature preview** in Settings (see the exact email signature before sending)
- **Provider test** button — send yourself a Gmail compose to verify authuser lock
- **Won streak widget** — small streak counter on the dashboard
- **Voice-to-note capture** — job-site dictation into any lead
- **Photo / estimate upload** — attach property photos and estimate PDFs to a lead
- **Referral prompt** — after Won status, prompt a text to ask for a referral
- **Weekly recap email** — "you contacted X, Y replied, Z estimates out"
- **Webhook persistence** to Mongo so preview reloads don't hijack production
- **iPad hint** — small nudge saying "open on iPhone to text"
