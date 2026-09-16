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

**Mobile BottomNav parity (2026-02-17)** — desktop Sidebar had grown to
include Discovery, Debug, and 4 sub-feed routes, but mobile BottomNav
still showed only Home / Projects / Settings. Rebuilt `BottomNav.jsx`
with 4 primary tabs (Home, Projects, Discovery, More) plus a bottom
Sheet drawer under "More" containing all secondary routes grouped by
section: Discovery Feeds (Property Managers, Real Estate Agents,
Landlords, Investors), Tools (Phone Lookup, Debug Panel), Preferences
(Settings). The Discovery tab now highlights amber for any `/discovery/*`
sub-route via `matchPrefix`. Every drawer row carries a
`more-link-{slug}` data-testid. Verified via mobile-viewport screenshots
(390x844): drawer opens, all 7 links present, Investors nav works, active
state persists. Fixes Ryan's complaint that "the phone site is severely
limited" — 50% of the app was unreachable on his primary device.

**Needs Enrichment section + Days-on-Table pill (2026-02-17)** — Ryan
complained the main lead list was polluted with dead-weight records that
had no score and no way to reach anyone, mixed in with workable leads.
Two fixes shipped together:

1. **Backend** — added `_days_on_table()` helper in
   `airtable_service.py` and injected `days_on_table` (integer or null)
   onto every Opportunity DTO from Airtable's `createdTime` metadata.
   Same code path already powered Discovery feeds; now the main leads
   table has it too.
2. **`queue.js`** — added three helpers: `hasChannel(opp)`,
   `hasGovernedScore(opp)`, `needsEnrichment(opp)`. A record qualifies as
   Needs Enrichment when it is NOT in Ready/Contacted AND either
   (a) the classifier explicitly tagged Contact Readiness / Enrichment
   Status / AI Status with "needs enrichment" / "needs research", OR
   (b) it has no governed score AND no reachable channel
   (email / email_alt / phone / phone_alt all empty).
3. **CommandCenter.jsx** — split the third bucket. "All Projects" now
   contains only records that have been enriched but aren't ready yet.
   A new **4 · Cold — Needs Enrichment** section appears below it,
   collapsed by default with a count. Verified live: 39 records
   correctly moved out of All Projects into the collapsed section on
   mobile, list is sorted oldest-first so stale ones surface for the
   enrichment pipeline. Rows use a compact `EnrichmentRow` (no
   messaging controls — read-only).
4. **Days-on-Table pill** — reused `DaysOnTable.jsx` (from Discovery
   feeds) on every row: ReadyRow, ContactedRow, AllProjectsRow,
   EnrichmentRow, and the generic `OpportunityRow` on `/opportunities`.
   Verified: 20 pills on Command Center, 59 on Opportunities.

**Enrichment Nudge — "Nudge Claude" one-tap (2026-02-17)** — every
Needs Enrichment row that has been on the table ≥ 30 days now shows a
"Stale" badge and a **Nudge Claude to enrich** button. Tapping the
button builds a compact governed-only prompt (name, address, type,
source URL, days on table, Airtable ID, and an explicit ask) and hands
it off natively:

- iOS PWA: `navigator.share({ title, text })` opens the native share
  sheet — Ryan picks Claude, Messages, Notes, whatever. AbortError
  from user-cancel is silent.
- Everywhere else: `navigator.clipboard.writeText()` copies the prompt
  and fires a sonner toast: *"Prompt copied — paste into your Claude
  thread."*

Preserves the strict outreach constraint (no backend automated sending)
and preserves the hard data boundary with Claude (never mutates the
Airtable schema; Ryan hands off the raw prompt himself). Verified live:
33 stale rows correctly picked up on mobile, prompt payload is well
formed, toast fires.

**Salutation bug fix — no business-name-as-first-name + no duplicate
greetings (2026-02-17)** — Ryan reported that opening a draft on a
business-only lead ("Tristan Construction LLC", "Backyard Living",
"Louisiana Land Art, LLC") was greeting "Hi Tristan," / "Hi Backyard,"
and, when the classifier had already put its own greeting on the
`first_message` field, the draft ended up with two stacked greetings.

Root cause was three unrelated builders (CommandCenter first + follow-up,
OpenInMessages first + follow-up, LandlordLetterPrint, Discovery real
estate agent pitch) all doing the same two things wrong:

  1. Fallback chain reached into `opp.name` — which in this app's
     schema is the record/project name, never a person.
  2. No stripping of an existing greeting on the classifier-provided
     body before prefixing a new one.

Extracted a shared helper `/app/frontend/src/lib/greeting.js`:

  - `looksLikeBusiness(name)` — regex-based detector for LLC / Inc /
    Corp / LLP / PC / Group / Holdings / Properties / Realty / Homes /
    Construction / Contracting / Design / Interiors / Studio / plus
    contractor-service tokens (Living / Pros / Kitchens / Baths /
    Roofing / Plumbing / Electric / HVAC / Landscaping / Painting /
    Cleaning / Handyman / Pool / Fencing / Flooring / Tile / Cabinetry
    / Countertops / Millwork / Art / Masonry / Concrete / Drywall /
    Framing / Windows / Doors / Gutters / Decks / Patios) and the
    conjunction pattern "X & Y" / "X and Y".
  - `personalFirstName(name)` — returns the safe first name or null
    when the string looks like a business.
  - `buildSalutation(candidates[], {verb, generic})` — accepts an
    ordered list of candidate name fields; callers only pass fields
    that are supposed to hold PERSON names (`decision_maker`,
    `contact_name`, `owner_name`, `agent_name`). `opp.name` is never
    passed. Falls back to a neutral generic ("Hi there," /
    "Dear Property Owner,") when no candidate is a real person.
  - `stripLeadingGreeting(body)` — removes a single leading
    "Hi/Hey/Hello/Dear X," or "Good morning/afternoon/evening X,"
    (plus trailing blank line) from a body so the builder can prefix a
    single well-formed greeting of its own. Idempotent; safe on empty.

Wired into every builder that touches a draft:

  - `pages/CommandCenter.jsx` — `buildFirstDraft`, `buildFollowUpDraft`
    (Ryan's Home Screen Email Now / Follow Up Email buttons)
  - `components/OpenInMessages.jsx` — same two, powering the panel on
    Opportunity Detail + the pill inside DraftNoteDrawer
  - `pages/LandlordLetterPrint.jsx` — landlord mailer letter body
    (verb "Dear", generic "Property Owner")
  - `pages/DiscoveryRealEstateAgents.jsx` — pre-listing pitch email

Regression fixtures under `src/lib/__tests__/greeting.test.js` (13
cases) exercise every real-world name shape from Ryan's data — all
pass. Live-verified via the OpenInMessages `<a href="mailto:…">` on
several records: business-only records now open with "Hi there," and
never stack a second greeting under a classifier-provided one.

## Ryan's ship order (confirmed 2026-02-16)
1. ✅ Learning loop shipped
2. ✅ Morning brief shipped
3. ✅ Preview wired to real Airtable
4. ✅ Reverse Lookup shipped
5. ✅ PWA Home Screen icon (custom cartoon character shipped 2026-02-17)
6. ✅ iOS Shortcut recipe for Reverse Lookup delivered (instructions only)
7. ✅ Perplexity Agent API integration (shipped 2026-02-18) — three
   one-tap web-grounded research features share `/api/research`:
   - **Who runs this?** on Opportunity Detail (research_type=`decision_maker`)
   - **Explain this permit** on Opportunity Detail (research_type=`permit_explainer`)
   - **Research this owner** on Discovery → Landlords (research_type=`landlord_background`)
   Backend uses the official `perplexityai` SDK with `preset="medium"`
   (bundles a web-grounded model + `web_search` + `fetch_url` tools).
   Mongo cache in `research_cache_service.py` (7-day TTL, keyed by
   `(research_type, record_id)`). API key from `PERPLEXITY_API_KEY`;
   missing key → clean 503 and buttons hide. Live-verified: 3.9KB
   grounded answers with 10 cited NOLA sources, cache round-trip
   returns `_cached: true`.
8. Referral prompt after Won — planned

## Code-review fixes (2026-02-19)
Response to functional code review of the P1–P7 batch on production
(https://hound-priorities.emergent.host). All three material findings
resolved in preview; awaits redeploy to reach prod.
- **HIGH — Saved View chips now filter for real.** Added a `view` query
  param to `GET /api/opportunities` and the CSV export endpoint. Backend
  helper `_apply_view` maps each chip to a strict governed-field predicate
  (Hot → `priority_band == "A"`, Fresh/Stale → `freshness`, Needs
  enrichment → mirror of `queue.js:needsEnrichment` in Python, Recently
  added → `created_time` desc). Frontend forwards `view` on both the list
  fetch and the export href. Verified: Hot returns 17 (all band A), Fresh
  52, Needs enrichment 39, Recently added sorted desc, All 59.
- **LOW — CSV `estimated_value` column.** `csv_export_service.py` had
  whitelisted `construction_value`, which doesn't exist on the DTO —
  column was always blank. Renamed to `estimated_value` to match
  `airtable_service.py`.
- **LOW — CSV now respects on-screen filters.** `csvOpportunitiesUrl`
  accepts a `URLSearchParams`; `SavedViewsBar` in Opportunities passes
  the current URL params so `?view=hot&status=Ready` etc. round-trip
  into the CSV. Backend endpoint accepts the same params as
  `/api/opportunities`.

## Backlog / Next
- **Partner-lead money model** — decide how to represent "estimated job value" on Partner-kind records (annual referral value? new dedicated field? leave blank?). Deferred by Ryan 2026-02-16.
- **Orphaned P1–P7 pieces** — `BulkActionBar.jsx`, `hooks/useLocalArchive.js`, `hooks/useTelemetry.js`, `csvDiscoveryUrl` are built but not wired in. Wire up or delete on next iteration.
- **Bound `POST /api/telemetry/event` payload size** server-side (flag off by default; low risk).
- **Signature preview** in Settings (see the exact email signature before sending)
- **Provider test** button — send yourself a Gmail compose to verify authuser lock
- **Won streak widget** — small streak counter on the dashboard
- **Voice-to-note capture** — job-site dictation into any lead
- **Photo / estimate upload** — attach property photos and estimate PDFs to a lead
- **Referral prompt** — after Won status, prompt a text to ask for a referral
- **Weekly recap email** — "you contacted X, Y replied, Z estimates out"
- **Webhook persistence** to Mongo so preview reloads don't hijack production
- **iPad hint** — small nudge saying "open on iPhone to text"

**Twilio Lookup v2 integration (2026-02-18)** — read-only phone-number
intelligence. First and only Twilio surface Bloodhound uses; the app's
"no automated outbound" rule stays intact.
- `services/twilio_lookup_service.py` wraps `client.lookups.v2` and
  requests `line_type_intelligence,caller_name` (~$0.015 per call).
  Returns normalized DTO: line_type, carrier_name, mobile country/
  network codes, caller_name, caller_type.
- Routes: `GET /api/lookup/twilio/{number}` + `GET /api/lookup/twilio/status`.
  Feature-flagged on TWILIO_ACCOUNT_SID (must start with `AC`) +
  TWILIO_AUTH_TOKEN. Missing → status returns `enabled:false`, GET
  returns 503, and the frontend hides the card entirely — no error banner.
- `components/TwilioIntel.jsx` auto-runs on mount for the number in the
  URL of the Reverse Lookup page. Renders line-type + carrier pills,
  CNAM name if available, and a "Likely burner / spam" chip when the
  number is non-fixed VoIP with no CNAM. Retry button on 429/5xx.
- Verified live with placeholders empty: status→`{enabled:false}`, lookup→503,
  page renders without the card (0 "Twilio" mentions in DOM).

**Credentials needed to turn it on (Ryan):**
1. Log into https://console.twilio.com/ → Account Info
2. Copy Account SID (starts with `AC…`) → paste as `TWILIO_ACCOUNT_SID`
3. Reveal Auth Token → paste as `TWILIO_AUTH_TOKEN`
4. Use the Emergent env-vars editor (secret-scoped), not chat.
5. Redeploy — the card will start rendering on `/lookup?phone=…` automatically.

**Perplexity research on Real Estate Agents (2026-02-18)** — mirror of
the Landlord research pattern. Every agent row now has a "Research
this agent" toggle that expands an inline `ResearchPanel` with a
dedicated `re_agent_background` system prompt tuned for: verified
public business email + phone (brokerage site / their own site /
Realtor.com / Zillow — never personal-looking numbers), recent NOLA
listings, 12-month sold volume, brokerage tenure, and specialty
(flips / historic / higher-end). Works regardless of Outreach Gate
state — research is read-only, no messages sent.

Live-verified on Mary Danna (Keller Williams): returned a 3.3KB grounded
answer with `mary@salepending.com`, `504-517-6533`, Metairie office
address, and 10 cited sources. Run button 44px (mobile-safe).

Ryan can now enrich locked agent rows without waiting on Claude,
then hand the verified contact off for the classifier to promote
the Outreach Gate on the Airtable side.

**Auto-fill Contact — the app's first Discovery-side write (2026-02-18)**
Ryan requested: when Perplexity returns a verified email/phone on an
agent, one-tap writes it into Airtable so the row shows up enriched
on production without waiting on Claude to paste it in.

Backend:
- `services/discovery_service.py` — added `DiscoveryReader.patch_fields`
  (small allowlist write path, invalidates cache on success) +
  `enrich_real_estate_agent(record_id, email, phone)` helper that only
  writes to `Email` and `Phone` columns. Never touches governed fields.
- `server.py` — new route `POST /api/discovery/real-estate-agents/{id}/enrich`.
  Airtable UNKNOWN_FIELD_NAME / 422 errors surface as a friendly 400
  telling Ryan the exact columns to add.

Frontend:
- `lib/contactExtract.js` — regex-based email + US phone extractor with
  a denylist for placeholder/fictional numbers. 4/4 unit cases pass.
- `components/ResearchPanel.jsx` — added `onResult` callback so parent
  components can react when a lookup finishes.
- `pages/DiscoveryRealEstateAgents.jsx` — the "Auto-fill contact" card
  renders inline below the ResearchPanel after a lookup completes:
  extracted email + phone in editable input fields (Ryan can correct
  before writing), a 44pt "Send to Airtable" button, sonner toast on
  success/error, row updates in place with the new contact.

Live-verified: extractor pulled mary@salepending.com + (504) 517-6533
from a real Perplexity answer; the write correctly failed with the
friendly-400 telling Ryan to add Email + Phone columns to the
"Real Estate Agent Outreach" table (they don't exist in his current
schema).

**Auto-fill self-heals — no dependence on Claude (2026-02-18)** — Ryan
requested this be an Emergent-owned function, not a Claude handoff.
Two upgrades to the Auto-fill Contact write path:

1. **Actual Airtable column names** — the Real Estate Agent Outreach
   table already had `Public Business Email` and `Public Business
   Phone` columns; the write helper now targets those exact names
   instead of the wrong-guess `Email` / `Phone`. DTO reader also
   updated to pull `public_business_email` / `public_business_phone`
   as the primary snake-keys.
2. **Auto-heal safety net** — added `DiscoveryReader.ensure_columns`
   using pyairtable's Metadata API (`Table.create_field`). If a write
   fails with UNKNOWN_FIELD_NAME (e.g. columns get renamed on Claude's
   side later), `patch_fields` auto-creates the missing columns as
   `singleLineText` and retries the write once. If the PAT lacks
   `schema.bases:write`, the route surfaces a clean 400 with the
   exact next step (rotate the PAT, no Claude involvement needed).

Live-verified: `POST /api/discovery/real-estate-agents/recwB56WOxRQwOijw/enrich`
returned HTTP 200 in ~1s; the live Airtable row now carries Mary
Danna's Perplexity-extracted email + phone; cache invalidated so the
Discovery feed reflects it immediately.

**P1-P7 compatible-pass shipped (2026-02-18)** — all seven priorities from the audit plan, no founding rule broken.

Files created:
- `backend/services/local_state_service.py` — Mongo `bloodhound_local_state`, namespaced by (workspace=solo, feed), archive/unarchive/list; feed allowlist blocks arbitrary paths.
- `backend/services/csv_export_service.py` — per-feed DTO whitelist + QUOTE_ALL + formula-injection guard (=/+/-/@/|/tab/CR prefixed with `'`).
- `frontend/src/components/ScoreExplanationCard.jsx` — governed Claude fields with provenance chips; "Not yet classified" when null.
- `frontend/src/components/ContactStatusChip.jsx` — 6 states derived from DTO only.
- `frontend/src/components/CommandCenterStats.jsx` — 4 zero-fabrication counters.
- `frontend/src/components/SavedViewsBar.jsx` — URL-driven bookmarkable views; 44px mobile / 32px desktop; carries the Export CSV link.
- `frontend/src/components/BulkActionBar.jsx` — 44px CTAs; BCC-first `mailto:` with URI-length fallback + explicit tab-count confirm; excludes records without email; Archive button title explains "Bloodhound only — Airtable/Make unchanged".
- `frontend/src/hooks/useLocalArchive.js` + `useTelemetry.js` — telemetry strictly non-blocking, off by default via `BLOODHOUND_TELEMETRY_ENABLED`.

Backend routes added:
- `GET /api/local-state/{feed}/archived` · `POST /archive` · `POST /unarchive` (feed allowlist)
- `POST /api/telemetry/event` (returns `{stored:false}` unless env flag on)
- `GET /api/exports/opportunities.csv` · `GET /api/exports/discovery/{feed}.csv` — `text/csv; charset=utf-8` + `Content-Disposition: attachment; filename=...`

Wired into: OpportunityDetail (ScoreExplanationCard + ContactStatusChip), CommandCenter (Stats top of page), Opportunities (SavedViewsBar w/ CSV export).

Regression sweep (all 200/expected): opportunities, discovery (all 4 feeds), perplexity status, twilio status, morning-brief 401 without bearer, archive round-trip, unknown feed rejected 400, CSV headers correct + 66-row payload.

No environment variables required beyond the existing set; `BLOODHOUND_TELEMETRY_ENABLED` is optional and defaults off.
