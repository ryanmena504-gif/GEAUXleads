# Airtable ↔ Make mapping

This document is the operator-facing companion to `GET /api/diagnostics/ingestion`.
It explains what the app reads, how to find a mapping gap, and what to change on
the Make side to close one.

**No credentials appear in this repository.** Everything below is configuration
that lives in the deployment environment or in the Make/Airtable UI.

## How data reaches the dashboard

```
source signal ──> Make.com scenario ──> Airtable `Leads` table ──> this app (read-only cache)
```

The app never creates, renames, or deletes an Airtable field. It reads the base
schema at startup and maps only the columns that actually exist. Anything it
expects but cannot find renders as *"Not available yet"* rather than a guess.

Writes are limited to a small allowlist of workflow-status columns
(`Approval status`, `Outreach status`, `Status`, `First message` for the Leads
service; plus `Hunt status`, `Next followup`, `Rejection reason`, `Notes` for the
opportunity service). Everything else is read-only by construction.

## The silent failure this is designed to catch

When a Make mapping is missing, nothing errors. The Airtable column exists, the
app reads it, and it is simply never populated — so the dashboard shows a blank
forever. `GET /api/diagnostics/ingestion` makes that visible by reporting the
populated-row percentage for every mapped column.

| `status` | Meaning | Action |
| --- | --- | --- |
| `never_populated` | 0% of records have a value | Almost certainly a missing output mapping in the Make scenario |
| `sparse` | under 25% populated | A conditional branch only maps the field on some paths, or an enrichment step fails silently |
| `ok` | 25%+ populated | Nothing to do |

The same endpoint reports:

- `mapping_gaps.expected_but_absent` — the app expects the column, Airtable does
  not have it. Add the column only if you want the data surfaced; no code change
  is needed either way.
- `mapping_gaps.present_but_unmapped` — Airtable has the column, the app does not
  read it. To surface it, add an entry to `LIVE_FIELDS` in
  `backend/services/airtable_service.py` or `LEADS_FIELD_MAP` in
  `backend/services/leads_service.py`.
- `issue_counts` / `issue_samples` — per-record values that are present but
  uninterpretable (see below).
- `pipeline_exceptions` — records that raised during projection and were dropped
  from the cache rather than taking the whole refresh down.
- `recommendations` — the above, phrased as concrete next steps.

## Make-side changes, by symptom

These are the fixes the diagnostic recommends. All are made in the scenario, not
in this app.

### `invalid_phone`

A stored value that is not a dialable 10-digit NANP number. The eligibility
policy treats such a lead as having **no phone at all**, so it will not be
approvable.

Normalize before the Airtable *Create/Update a Record* module: strip country
prefixes, extensions (`x123`, `ext. 4`), and punctuation. Write a blank rather
than raw scraped text when normalization fails — a blank is honest, a broken
number looks contactable and is not.

### `invalid_email` / `placeholder_email`

Either unparsable, or a placeholder the app refuses to treat as reachable:
`noreply@`, `no-reply@`, `donotreply@`, `example.com`, `test@`, `info@example…`.

Validate the enrichment output before mapping it. Write blank when the enricher
returns a placeholder.

### `unparsable_money`

A currency column holding text (`"$45,000 - $60,000"`, `"TBD"`). Text money
values are **excluded from pipeline totals** — they do not silently count as
zero. Either retype the Airtable column as Currency/Number, or strip formatting
in the scenario.

### `unparsable_date`

Emit ISO-8601 (`YYYY-MM-DD`) from the scenario. The app also accepts
`MM/DD/YYYY`, `DD/MM/YYYY`, `YYYY/MM/DD`, and `Mon DD, YYYY`, but ISO is
unambiguous and should be preferred.

### `missing_contact` / `missing_address` / `missing_category`

Coverage gaps rather than errors, but each one blocks outreach on its own. If a
whole column shows these at high volume, check whether the enrichment branch that
populates it is running for every path through the scenario.

## Columns that matter most to outreach eligibility

A lead cannot be approved without all of these. Prioritize their mappings.

| Requirement | Airtable columns consulted (first non-empty wins) |
| --- | --- |
| Reachable contact | `Contact phone`, `Phone number` / `Contact email`, `Email` |
| Street address | `Address` (must contain a street number, not just a city) |
| Counterparty | `Contact name` — or `Contact company` / `Business name` as the organizational equivalent |
| Category | `Opportunity type` (falls back to project type / source category) |
| Confidence | `contact confidence` |
| Risk | `Risk flags` |

### On "decision maker"

The requirement is an identified decision maker / owner / applicant / contractor.
The live `Leads` table has **no** `Applicant`, `Contractor`, or `Owner` columns —
they are listed in `PENDING_FIELDS` and render as "Not available yet". The
implemented equivalent is:

1. A named person in `Contact name` — treated as a full match.
2. Failing that, a named business in `Contact company` / `Business name` — accepted,
   but recorded as an `org_only_counterparty` warning so the operator knows they
   are contacting a company rather than a named individual.

If Make later starts writing `Applicant` / `Contractor` / `Owner`, add those
columns to `FIELD_ALIASES["counterparty_person"]` in
`backend/services/outreach_policy.py`; no other change is required.

## Duplicate identity

Duplicates are detected from field values on every cache refresh — **nothing is
written to Airtable**. Two records merge into one group when they share any of:

- a 10-digit phone
- a normalized email
- a permit number
- a normalized street address
- a name scoped to a city (only when the name is specific enough to be unlikely
  to collide)

One canonical record per group is elected (richest, then oldest, then lowest
record id — a total order, so the election is reproducible). Non-canonical
members are excluded from counts, lists, and the action queue, so the same
homeowner cannot be messaged twice from two cards.

Resolving a duplicate in Airtable (correcting a phone, clearing an address)
changes the grouping on the next refresh. There is no stored state to migrate.

Inspect the current grouping at `GET /api/leads/duplicates` and
`GET /api/opportunities/duplicates`; `matched_on` states which key caused each
merge.

## Configuration

All environment variables. None are committed.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AIRTABLE_ENABLED` | *(unset)* | `true` enables the live backend |
| `AIRTABLE_API_KEY` | — | Needs `data.records:read`, `data.records:write`, `schema.bases:read` |
| `AIRTABLE_BASE_ID` | — | |
| `AIRTABLE_OPPORTUNITIES_TABLE` | — | Table backing the dashboard (currently `Leads`) |
| `AIRTABLE_LEADS_TABLE` | `Leads` | Table backing Next Best Action |
| `BLOODHOUND_OPERATOR` | `operator` | Default actor on audit events |

### Outreach policy thresholds

Tunable without a code change. Booleans accept `true/1/yes/on`.

| Variable | Default | Effect |
| --- | --- | --- |
| `OUTREACH_MIN_SCORE` | `50` | Minimum readiness score to approve |
| `OUTREACH_MIN_CONTACT_CONFIDENCE` | `medium` | `low` / `medium` / `high`; unset confidence warns rather than blocks |
| `OUTREACH_REQUIRE_ADDRESS` | `true` | Require a street address |
| `OUTREACH_REQUIRE_CATEGORY` | `true` | Require a project/service category |
| `OUTREACH_REQUIRE_COUNTERPARTY` | `true` | Require a named person or business |
| `OUTREACH_BLOCK_ON_RISK` | `true` | Block on a blocking risk flag |
| `OUTREACH_BLOCK_DUPLICATES` | `true` | Block approval of a non-canonical duplicate |
| `OUTREACH_BLOCK_ALREADY_SENT` | `true` | Block re-contacting a lead already marked sent |

Note on `OUTREACH_MIN_SCORE`: the base's `Lead score` column is `0` on most rows
today. The policy therefore uses `Lead score` only when it is greater than zero,
and otherwise computes a readiness score from live field values. The response
reports which was used via `score_source` (`airtable_lead_score` or
`computed_from_live_fields`), so raising the threshold does not silently block
every lead.
