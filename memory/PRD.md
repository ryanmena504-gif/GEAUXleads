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

## Governed current-state layer (2026-02-16)
The dashboard's three lists and every action gate are driven STRICTLY by
17 read-only Airtable fields set by the Make classifier. The frontend never
recalculates, infers, fuzzy-matches, or falls back to legacy fields.

**Field → DTO mapping (17 governed fields):**
| Airtable field         | DTO key                  | Governed role                          |
| ---------------------- | ------------------------ | -------------------------------------- |
| Current Queue          | current_queue            | Bucket placement (Ready / Contacted / All) |
| Contact Readiness      | contact_readiness        | Paused + not-ready reason              |
| Contact State          | contact_state            | Follow-up / lifecycle context only     |
| Money Signal           | money_signal             | Chip on Ready rows                     |
| Operator Activity      | operator_activity        | Context only — DOES NOT drive Paused   |
| Premium Fit            | premium_fit              | Chip on Ready rows                     |
| Evidence Status        | evidence_status          | Chip on Ready + All Projects rows      |
| Freshness              | freshness                | Sort tiebreak (Current→Aging→Stale)    |
| Governed Priority Score| governed_priority_score  | Primary sort within a bucket           |
| Score Basis            | score_basis              | Score-detail disclosure                |
| Priority Explanation   | priority_explanation     | "Why this matters" copy on Ready rows  |
| Current Recommendation | current_recommendation   | "What to do next" copy                 |
| Public Contact Evidence| public_contact_evidence  | Evidence disclosure on Ready rows      |
| Contact Verified Date  | contact_verified_date    | Evidence disclosure timestamp          |
| Project Fit Reason     | project_fit_reason       | "Fit reason" copy on Ready rows        |
| Last Classified At     | last_classified_at       | Audit only                             |
| Classification Version | classification_version   | Audit only                             |

**Confirmed invariants (verified end-to-end 2026-02-16):**
- Current Queue alone controls Ready to Contact, Contacted, and All Projects placement (strict exact-string equality).
- Contact Readiness alone controls Paused and every other not-ready reason.
- Contact State only supplies follow-up / lifecycle context on Contacted rows.
- No legacy field, fallback, fuzzy match, inferred phone/email condition, or sample-only flag can override governed state.
- Opening an email or text draft writes nothing and changes no state (device-native `mailto:` / `sms:` only).

### Ready-to-Contact source chips (2026-02-16)
- One-tap Source chip on every Ready to Contact row when `source_url` is
  present on the record. Opens the origin (permit filing, referral note,
  post URL, etc.) in a new tab. `stopPropagation` on the anchor so tapping
  the chip never fires the row's Open Detail navigation. Purely a link —
  writes nothing, changes no state.

## Zero backend writes on draft-open (2026-02-16)
Opening any native draft handoff — Open Email Draft, Open Text Draft,
Open Follow-Up Draft, Draft-a-Note button, drawer open, drawer copy,
plain record view — now causes ZERO writes to our backend. The
`api.logHandoff` call was removed from `OpenInMessages.jsx` on every
tap path; `onEmailTap` is a no-op and `onTextTap` only mutates local UI
state. The follow-up EmailButton has no `onClick` handler at all.

The `POST /api/opportunities/{id}/result` write on `result-sent` is the
ONLY explicit outcome path that touches the backend on Ryan's tap. It
runs only after he confirms "I sent it," it does not change Current
Queue / Contact Readiness / Contact State (governed fields stay owned by
Airtable + Make), and it is not a side effect of preparing a draft.

Verified by iteration_10 Playwright request interception + DB delta
check (test files: `test_iteration_10_no_write_on_draft.py`,
`test_iteration_9_governed_leaks.py`).

## Global governed-queue gating (2026-02-16)
`outreachAllowed(opp)` in `/app/frontend/src/lib/queue.js` is now the SINGLE
gate every messaging/drafting control routes through. It reads `current_queue`
verbatim and returns one of three values:

- `first_contact` (Current Queue = "Ready to Contact"): Open Email Draft;
  Open Text Draft only when SMS Permission is granted; Draft-a-Note allowed
  for partners; "I sent it" outcome button visible.
- `follow_up` (Current Queue = "Contacted"): exactly ONE Open Follow-Up
  Draft button. Text / Email / Contact them / Draft a Note / I sent it all
  hidden. Non-message outcome buttons (replied / estimate / no-reply /
  not-interested / Won / Lost) remain.
- `none` (everything else including "All Projects" and unclassified):
  ZERO messaging or draft controls anywhere in the app. Status buttons
  (Won / Lost / Get more info first) remain — they're non-message state
  changes.

Enforcement surfaces:
- OpenInMessages component (panel + pill variants) gates internally, so
  every caller — dashboard, opportunity detail, People to Know, Time to
  Nudge, Draft-a-Note drawer footer — inherits the same rule.
- ContactResults strips "I sent it" outside `first_contact` and returns
  null on `none`.
- NextBestAction and Relationships gate the Draft-a-Note button by
  `outreachAllowed(opp) === "first_contact"`.
- OpportunityDetail hero now leads with governed badges (Current Queue,
  Contact Readiness, Contact State) and a large Governed Priority Score.
  Money Signal / Premium Fit / Evidence Status / Freshness render as
  primary signals. Priority Explanation / Current Recommendation /
  Project Fit Reason follow. Legacy meters remain under "More details ·
  legacy signals" with `opacity-70` so they never visually outrank the
  governed layer.

## Sidebar + filter cleanup (2026-02-16)
- Sidebar: `Today` → `Home`; `People to Know` link removed. Route
  `/relationships` remains directly reachable.
- BottomNav: 3 columns — Home / Projects / Settings.
- All Projects `Lane` filter: exposes only `market_capture`. `partner`
  and `non_permit` are still valid record-level classifications but no
  longer visible operating buckets.

## Learning loop (2026-02-16)
Read-only outcome-aggregation layer. `/api/learning/insights` scans the
opportunity list, computes reply-rate and win-rate per governed dimension
(Money Signal, Premium Fit, Freshness, Evidence Status, Source), and ranks
patterns by |delta from baseline| × sqrt(sample size). Frontend
`LearningStrip` renders up to 3 insights above the three-list dashboard.

Guarantees:
- Zero writes. Never mutates opportunities, Airtable, or any store.
- Zero LLM. Pure Python aggregation.
- Sample-safe. Requires ≥3 observations per bucket AND ≥6 total outcomes.
- Silent when there isn't enough signal — the dashboard stays calm.

Sample fixtures now include `outreach_status` on 8 records so the strip
demonstrates end-to-end. When Airtable is wired, the same aggregation runs
live against confirmed outcomes.

## Morning Brief (2026-02-16)
Ryan's daily 7am glance — one email + an in-app panel from the same source.

- Backend `services/morning_brief_service.py` composes three sections:
  New Ready (≤ 24h since `last_classified_at` and `Current Queue = "Ready to Contact"`),
  Follow-ups due (same buckets as `/api/follow-ups/due`),
  Estimate deadlines (`outreach_status ∈ {Estimate requested, Estimate sent}` ≥ 7 days).
- Endpoints: `GET /api/morning-brief/preview` (frontend + testing) and
  `POST /api/morning-brief/send-now` (Settings "test send" hook).
- Cron: `.emergent/crons.yml` fires `POST /api/cron/morning-brief` at
  07:00 America/Chicago; the endpoint requires `Bearer WEBHOOK_CRON_SECRET`
  and background-schedules the send so the platform gets an immediate 2xx.
- Delivery: Emergent-managed Resend via the guardrail-gated
  `send_outreach_email` helper (G2 + G3 structural checks on every send).
  Recipient is `user_settings.sender_email` — currently
  `ryanmena@theshirtlesshandyman.com`.
- Frontend `MorningBrief.jsx` renders the same content at the top of Home
  when the day's brief has ≥ 1 row; dismiss is UI-only via localStorage,
  never hits the backend.

## Email Now workflow (2026-02-16)
Collapsed every outreach entry point into ONE button per record type:

- **Ready to Contact**: single primary button `Email Now`. One tap → native
  `mailto:` with the verified public business email + playbook subject +
  personalized playbook body + signature. No intermediate modal, drawer,
  template picker, copy button, preview, or second action.
- **Contacted**: single button `Follow Up Email` with a preloaded follow-up
  body via mailto. Initial-contact controls stay hidden.
- **All Projects**: zero email / text / draft / message controls.

Retired everywhere: `Open Email Draft`, `Open Text Draft`, `Open Follow-Up
Draft`, `Draft a Note` button (partner card + NextBestAction + Detail hero),
DraftNoteDrawer as an outreach entry point, SMS-first fallback on Ready
records. The `Draft a Note` button is gone from every visible surface;
`DraftNoteDrawer.jsx` file remains on disk but is now unreachable via UI.

Guarantees preserved:
- Clicking Email Now or Follow Up Email makes ZERO backend writes.
- No handoff endpoint call, no audit log, no Airtable write, no
  contact_handoffs row, no Current Queue / Contact State / outreach-status
  / approval-status / governed-field mutation.
- No Gmail API / Resend / Twilio / SMTP / campaign system for lead
  outreach. Browser opens a plain `mailto:` — Ryan presses Send himself.
- If no verified public business email is on file, `Email Now` does NOT
  render. SMS is never substituted just because a phone number exists.

Message Playbooks editor in Settings is untouched — the Email Now button
consumes the current playbook values (`first_message_subject`, `first_message`,
`current_recommendation` for follow-ups) automatically.

## Preview wired to real Airtable + money display (2026-02-16)
Fresh PAT swapped into `/app/backend/.env`; backend flipped from `sample`
to `airtable` with **49 real records** (8 Ready to Contact / 2 Contacted /
39 All Projects).

Diagnosis of the "no money in production" report: the real Airtable base
has ZERO populated numeric currency values on every record (`Estimated job
value`, `Closed revenue`, `Estimated gross profit`, `Permit project value`
all empty on all 49). Two formula fields — `Official project value` and
`Estimated opportunity value` — compute over those empty currency cells and
return the placeholder strings `"Not public"` and `"Not estimated yet"` on
every record.

Fix (transparent, no fake numbers):
- Airtable mapper now reads three additional money-related fields:
  `Official project value → official_project_value`,
  `Estimated opportunity value → opportunity_value_display`,
  `Permit project value → permit_project_value`.
- New frontend helper `moneyDisplay(opp)` in `formatters.js` prefers
  `estimated_value` (number → `$185K`), else falls back to the Airtable
  formula strings in order:
  `opportunity_value_display → official_project_value → revenue_potential`.
- Home Ready rows + Opportunity Detail hero now use `moneyDisplay()`, so
  the app matches what Ryan sees inside Airtable. When Ryan populates
  `Estimated job value` on a record, the numeric badge lights up
  automatically on the next refresh.

## Reverse Lookup + Playbook fallback + PWA Home Screen icon (2026-02-16)
Three ships in one pass:

**Reverse Lookup** — new endpoint `GET /api/opportunities/by-phone/{number}`
normalizes any inbound phone (strips `+1`, spaces, dashes, parens) then
matches against `phone`, `phone_alt`, `contact_phone` on all 49 live
records. Prefers the highest-priority Ready-to-Contact match, then
Contacted, then anything else. Verified live: `(985) 626-7619` → Ron Lee
Homes / RLH Construction (Ready, Score 90), `(985) 875-7576` → Greige
Interiors (Contacted, Score 64). New page `/lookup?phone=...` renders a
compact governed card with Email Now / Follow Up Email button, Why This
Matters, What To Do Next, Readiness, Contact State, and a link to the
full record. Read-only — never mutates the record.

**Playbook fallback rewritten** — Home Screen `Email Now` now uses
partner-appropriate copy when Make hasn't drafted the record yet (7/8
Ready records have empty `First message`). The fallback mirrors the
approved language format Make uses on the one drafted record (Tristan
Construction). Preserves priority: real `first_message` → `first_contact_message`
→ smart fallback based on `lane === 'partner'`.

**PWA Home Screen install** — added `manifest.json`, `apple-touch-icon.png`
(180x180), `icon-192.png`, `icon-512.png`, `favicon-32.png`, and iOS
meta tags to `index.html`. Ryan opens the preview on his iPhone in Safari
→ Share → Add to Home Screen → Bloodhound icon lands on his Home Screen
→ tapping opens the app full-screen (no Safari chrome).

**Custom Home Screen icon (2026-02-17)** — Ryan uploaded his Shirtless
Handyman cartoon character artwork; all four icon files were regenerated
from the 1024x1024 source at proper sizes (180/192/512/32) with Lanczos
resampling. Manifest `purpose` set to `any` (no maskable crop) so the
character composition is preserved edge-to-edge on iOS Home Screen.

## Ryan's ship order (confirmed 2026-02-16)
1. ✅ Learning loop shipped
2. ✅ Morning brief shipped
3. ✅ Preview wired to real Airtable
4. ✅ Reverse Lookup shipped
5. ✅ PWA Home Screen icon (custom cartoon character shipped 2026-02-17)
6. ✅ iOS Shortcut recipe for Reverse Lookup delivered (instructions only)
7. Referral prompt after Won — planned

## Backlog / Next
- **Partner-lead money model** — decide how to represent "estimated job value" on Partner-kind records (annual referral value? new dedicated field? leave blank?). Deferred by Ryan 2026-02-16.
- **Signature preview** in Settings (see the exact email signature before sending)
- **Provider test** button — send yourself a Gmail compose to verify authuser lock
- **Won streak widget** — small streak counter on the dashboard
- **Voice-to-note capture** — job-site dictation into any lead
- **Photo / estimate upload** — attach property photos and estimate PDFs to a lead
- **Referral prompt** — after Won status, prompt a text to ask for a referral
- **Weekly recap email** — "you contacted X, Y replied, Z estimates out"
- **Webhook persistence** to Mongo so preview reloads don't hijack production
- **iPad hint** — small nudge saying "open on iPhone to text"
