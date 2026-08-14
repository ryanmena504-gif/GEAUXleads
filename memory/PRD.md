# BLOODHOUND — AI Opportunity Intelligence · PRD

## Original problem
A premium full-stack app for contractors (Ryan) that discovers, understands, and
prioritizes business opportunities and partners. Airtable `Leads` table is the
source of truth. Everything outbound is **native iOS handoff only** (`sms:` and
`mailto:`). **No automated backend sending** (no Resend, Twilio, Gmail APIs).

## Product principles
- Plain English everywhere. Hide scores/bands/database jargon.
- Manual result buttons are the ONLY way outreach status advances.
- Opening a draft NEVER writes to Airtable.
- Records are NEVER dropped, archived, hidden, or retired because contact
  info is missing. The AI keeps learning from the same set.
- No probabilities, expected-value dollars, or AI-generated win claims
  appear unless enough confirmed outcomes exist.

## Core requirements (implemented)
- **4-item navigation** (Sidebar + BottomNav): Today · All Projects · People to
  Know · Settings.
- **Today page = 3 work buckets**: Contact Now · Watch · Not a Fit. Everything
  else lives behind the record detail page.
- **Manual result buttons** on `/opportunities/:id`: I sent it, They replied,
  Estimate requested, No reply yet, Not interested — with an **optional note
  textarea** that gets stamped into Airtable Notes.
- **Needs confirmation banner** when outreach history is ambiguous.
- **AI Contact Enrichment (manual only)** — Gemini 2.5 Flash + Google Search
  grounding. Toggle defaults OFF. Business-only contacts. 30-day recheck.
  Nothing archived automatically.
- **Bloodhound learning loop** (branch `computer/bloodhound-learning-loop`,
  commit `bfe32e2`, pulled 2026-08-14):
  - `services/predictive_engine.py` — evidence-first recommender. Returns
    `work_bucket`, `priority`, `why_this_matters`, `what_to_do_next`,
    `learning_note`, `evidence_gaps`. **Always returns
    `conversion_probability=null`, `expected_value=null`, `priority_score=null`.**
    Only produces "pattern found" language when ≥5 confirmed outcomes exist.
  - `services/reply_intelligence.py` — regex-based reply classifier
    (estimate_request / positive / not_interested / needs_info / referral /
    unclear). Never mines notes; only reads `reply_summary`. Suggests a
    manual next step; changes nothing.
  - `services/market_intelligence.py` — city / project-type / velocity
    counts derived from live records. Never claims revenue.
  - `services/field_norm.py` — shared normalization helpers.
  - `tests/test_bloodhound_learning.py` — 6 tests, all passing.
  - Endpoints: `/api/intelligence/predictive/status`,
    `/api/intelligence/predictive/train`,
    `/api/intelligence/predictive/{id}`,
    `/api/intelligence/predictive/batch/top`,
    `/api/intelligence/market`,
    `/api/intelligence/reply/classify`,
    `/api/intelligence/reply/leads-with-replies`.
  - Frontend: `PredictiveScoreBadge` inside the opportunity detail's action
    panel (shows Why/What/Learning note/Evidence gaps).
    `ReplyIntelligencePanel` renders only when the record has a real
    `reply_summary`. `Intelligence.jsx` page is available at `/intelligence`.

## Recent changelog
- 2026-08-14 — Pulled `computer/bloodhound-learning-loop@bfe32e2`. Added 4
  new backend services, 3 new frontend components, Intelligence page,
  6 backend tests, 7 new API endpoints, optional note on result buttons.
  Commit `77e73da`.
- 2026-02-11 (final) — Removed 5-day soft-archive rule; added 3-bucket Today
  page; tightened LLM prompt to reject homeowner/private/permit contacts;
  30-day recheck marking on no-hit records; confirmation modal on per-lead
  enrichment button; restored 22 previously affected records.
- 2026-02-11 — Per-lead enrichment button + AI Contact Enrichment sweep.
- 2026-02-11 — Rewrote CommandCenter into strict 3-section Today page.

## Backlog
### P1 — Recheck-driven surfacing
- Highlight records whose 30-day recheck date has passed in a Watch
  sub-bucket. Never runs enrichment automatically.

### P2 — Webhook persistence
- Persist Airtable webhook state to Mongo so preview reloads don't hijack
  the production webhook.

### P3 — Small polish
- Source URL + reason chip on Contact Now rows.
- Unify BottomNav testids to `nav-*` prefix.
- Wire an in-app "What Bloodhound is learning" link inside Settings that
  points at `/intelligence`.

## Files of interest
- `/app/frontend/src/pages/CommandCenter.jsx` — 3-bucket Today.
- `/app/frontend/src/pages/OpportunityDetail.jsx` — manual result buttons,
  optional note, Needs confirmation, Find public business contact,
  PredictiveScoreBadge, ReplyIntelligencePanel.
- `/app/frontend/src/pages/Intelligence.jsx` — learning-loop overview.
- `/app/frontend/src/pages/Settings.jsx` — SenderIdentity + Enrichment.
- `/app/frontend/src/lib/priority.js` — contactReady, hasPremiumFit,
  needsConfirmation, isBusinessContact, isClosedOrBlocked.
- `/app/frontend/src/components/PredictiveScoreBadge.jsx`
- `/app/frontend/src/components/ReplyIntelligencePanel.jsx`
- `/app/frontend/src/components/ContactResults.jsx`
- `/app/backend/server.py` — result / enrich / intelligence endpoints.
- `/app/backend/services/enrichment_service.py`
- `/app/backend/services/predictive_engine.py`
- `/app/backend/services/reply_intelligence.py`
- `/app/backend/services/market_intelligence.py`
- `/app/backend/services/field_norm.py`
- `/app/backend/tests/test_bloodhound_learning.py`
