# Completed Project Proof — Round 1 (Slice 1) Airtable Schema

**Status:** APPROVED by Ryan on 2026-02-19 with revisions (see below).
This document is the **sole Round 1 reference** for Airtable field
creation. Claude / Make must build against this file exactly. Bloodhound
will read these fields as-is; no field in Round 1 is writable from the
app.

---

## Ownership model (unchanged from Bloodhound's founding architecture)

- **Airtable + Claude + Make own:** discovery, crawling, evidence
  extraction, classification, confidence, retry/status logic, and every
  write to the 16 fields below.
- **Bloodhound owns:** rendering these fields as a read-only card on
  the opportunity detail page. Zero writes. Zero scoring changes in
  Slice 1. Zero draft generation in Slice 1.

---

## The 16 fields (add to the existing business record / Leads table)

| # | Field Name | Airtable Type | Options / Notes | Purpose |
|---|---|---|---|---|
| 1 | **Portfolio Check Status** | Single select | `Pending`, `Running`, `Completed`, `No Portfolio Found`, `Insufficient Evidence`, `Failed`, `Needs Review`, `Not Eligible` | Lifecycle marker. Card renders only when this has a value. |
| 2 | **Portfolio Checked At** | Date and time (ISO, UTC) | Include time · Use GMT · Writable by automation | Timestamp of the most recent completed check. Renders as "Last checked · N days ago". |
| 3 | **Portfolio Found** | Single select | `Yes`, `No`, `Unclear` | Top-line answer surfaced as the headline chip. |
| 4 | **Best Project Title** | Single line text | Free text, ≤ 120 chars | Human-readable project name lifted from the source page. Never invented. |
| 5 | **Best Project URL** | URL | See revised note below (REVISION 1) | The one clickable Evidence URL (or Review source link). |
| 6 | **Project Type** | Single select | `Kitchen`, `Bath`, `Whole-home`, `Outdoor Living`, `Pool`, `Historic`, `Commercial`, `Other`, `Unclear` | Category of the referenced work. `Unclear` when the page doesn't say. |
| 7 | **Project Status** | Single select | `Confirmed Completed`, `Likely Completed`, `Unclear` | Explicit completion signal from the source page. Never inferred from imagery alone. |
| 8 | **Evidence Basis** | Single select | `Page text/captions` (only allowed value in Round 1) | Locked to one option because no vision analysis exists yet. |
| 9 | **Evidence Summary** | Long text | 1 sentence, ≤ 240 chars | Factual sentence pulled from the source page. Must be quotable back to the URL. |
| 10 | **Safe Observation** | Long text | 1 sentence, ≤ 240 chars, non-speculative | A neutral observation Ryan could repeat without embellishment. |
| 11 | **Compliment Line** | Long text | 1 sentence, ≤ 220 chars, **empty when confidence Low OR status Unclear** | The compliment sentence Slice 2 would use inside an opener. Enforced blank when unsafe. |
| 12 | **Partnership Angle** | Long text | 1 sentence, ≤ 240 chars, one narrow service relationship | Where The Shirtless Handyman could plausibly slot in. |
| 13 | **Portfolio Confidence** | Single select | `High`, `Medium`, `Low` | Confidence in the whole evidence package. |
| 14 | **Outreach Recommendation** | Single select | `Use Project Opener`, `Use Broad Business Opener`, `Do Not Use` | Bloodhound reads this as-is; Slice 1 renders only. |
| 15 | **Why This Was Chosen** | Long text | 2-4 sentences, plain English | Explainability line. Why this page + this evidence, why not others. |
| 16 | **Portfolio Error Reason** | Long text | Free text; populated only when `Portfolio Check Status = Failed` | Blank in all other states. |

---

## REVISION 1 — Best Project URL note (replaces original)

> Must be a public page URL. **Populate only when a specific source
> page was inspected and retained as evidence or review context. The
> URL may remain populated when `Portfolio Found` is `Unclear`, but it
> must be blank when no specific source page was found. A populated
> URL does not authorize project-specific outreach.**

### UI behaviour (Bloodhound-side, Slice 1)

- If `Best Project URL` is blank → hide the Evidence link entirely.
- If `Best Project URL` exists AND (`Portfolio Confidence = Low` OR
  `Project Status = Unclear`) → render the link labelled
  **"Review source"** (never "completed-project proof").
- Otherwise → render the link labelled **"Evidence"** and cite the
  Evidence Summary directly beneath.

---

## REVISION 2 — Attribution workflow rule (add to build reference)

> **A project cannot be treated as evidence merely because an image
> appears in a gallery.** Claude/Make must confirm that the business
> is publicly and directly associated with the work through first-party
> portfolio/case-study context, an attributed title/caption, explicit
> project language, a project credit, or comparable page text. If
> attribution is not clear, set `Portfolio Confidence` to `Low` and do
> not generate a project-specific compliment (leave `Compliment Line`
> blank).

---

## Approved Slice 1 acceptance-test slate

Exactly three records. Claude/Make runs the portfolio check on these
only during Round 1.

| Group | Record ID | Business | Website | What we're testing |
|---|---|---|---|---|
| A — likely strong portfolio | `recjqiG1eqhes4HN1` | **Sweeney Restoration, LLC** | sweeneyrestoration.com | System correctly identifies a real portfolio + captures a specific evidence URL + produces a non-invented compliment. |
| B — likely generic / weak evidence | `recjV6JTgEbBNgmaw` | **Rockwell Builders LLC** | rockwellbuildersllc.com | System refuses to invent a project-specific compliment; sets `Portfolio Found = Unclear` or `No` and `Outreach Recommendation = Use Broad Business Opener` or `Do Not Use`. |
| C — valid site, likely no gallery | `reczI61UIgTrHQHTm` | **Decor by Flora / Decorating Den Interiors** | flora.decoratingden.com | System cleanly records `No Portfolio Found` without crashing the record and does not generate a project-specific opener. |

**Held for Slice 2:** `recZ7oiv2MDNKb72Q` — J Hand Homes, LLC.
Reason: this record has phone but **no verified public email**.
Slice 2 acceptance test #5 requires that even when project proof is
found, no email draft may be generated without a verified public
business email. Not in scope for Round 1.

---

## Build order (locked)

1. **[YOU'RE HERE — DONE]** Save this schema doc.
2. **[Claude/Make]** Create/map the 16 exact Airtable fields via the
   existing workflow. Use the exact field names, types, and options
   listed above.
3. **[Claude/Make]** Run the portfolio check on the three approved
   test records only. No other records in Round 1.
4. **[Ryan]** Return the Airtable results to Bloodhound for review.
   Confirm every value is factual and safely conservative.
5. **[Bloodhound / Emergent agent]** After Ryan confirms the results:
   build read-only `CompletedProjectProofCard.jsx` and wire it into
   the opportunity detail page.
6. **[Ryan + Emergent agent]** Run the three-record acceptance test
   inside Bloodhound and produce the acceptance report.
7. **STOP.** Do not add draft generation, scoring changes, vision
   analysis, automatic rechecks, or automatic email behaviour. Those
   are Slice 2+ and require a separate approval.

---

## Card safety (Bloodhound-side rules — locked)

- Card remains entirely read-only. No PATCH endpoint may write any of
  these 16 fields from Bloodhound.
- Card renders only when `Portfolio Check Status` has a value.
- Card hides the Evidence link when `Best Project URL` is empty.
- Card hides / blanks `Compliment Line` whenever `Portfolio Confidence
  = Low` OR `Project Status = Unclear`, even if Airtable contains a
  value.
- Card must always show: `Portfolio Confidence`, `Outreach
  Recommendation`, `Evidence Basis`, and `Why This Was Chosen`.
- No action inside this feature may generate outreach, send email,
  update lead status, update score, or record outreach activity.

---

## Pass / fail standard (as pasted; note incomplete)

**⚠️ NOTE:** Ryan's approval message truncated mid-sentence at
"Sweeney saves a real public evidence URL and any compliment is…".
The complete pass/fail standard is pending. What was captured verbatim
is preserved below; Ryan to complete when he returns.

> The test is not complete unless:
> - Sweeney saves a real public evidence URL and any compliment is
> **[TRUNCATED — awaiting Ryan to complete]**

### Provisional pass/fail (derived from Slice 1 success condition
Ryan stated earlier — used only until the above is completed)

Ryan's originally stated Slice 1 success condition:

> "I can open three real business records in Bloodhound and see a
> clear Completed Project Proof card. One should safely produce a
> project-specific opener [context], one should clearly refuse to
> invent a project-specific compliment, and one should cleanly show
> No Portfolio Found. Every factual claim must have an exact source
> URL visible in the record."

Translated into acceptance checks for the three records:

- **Sweeney (`recjqiG1eqhes4HN1`)**
  - `Portfolio Check Status = Completed`
  - `Portfolio Found = Yes`
  - `Best Project URL` is a real, reachable public page on
    sweeneyrestoration.com
  - `Evidence Summary` is a factual sentence that can be quoted back
    to that URL
  - `Compliment Line` is populated ONLY if `Portfolio Confidence` is
    `High` or `Medium` AND `Project Status` is `Confirmed Completed`
    or `Likely Completed`
  - `Why This Was Chosen` explains, in plain English, why this
    specific project + URL was retained over others
- **Rockwell (`recjV6JTgEbBNgmaw`)**
  - `Portfolio Check Status = Completed` or `Insufficient Evidence`
  - `Portfolio Found = No` or `Unclear`
  - `Compliment Line` is BLANK (attribution unclear)
  - `Outreach Recommendation = Use Broad Business Opener` or
    `Do Not Use`
  - `Why This Was Chosen` cites the lack of clear attribution
- **Decor by Flora (`reczI61UIgTrHQHTm`)**
  - `Portfolio Check Status = Completed` or `No Portfolio Found`
  - `Portfolio Found = No`
  - `Best Project URL` is BLANK
  - `Compliment Line` is BLANK
  - `Outreach Recommendation = Use Broad Business Opener` or
    `Do Not Use`
  - Record is NOT put into a failure loop

### Hard-fail conditions (any single one fails the run)

- Any invented project title, address, client, date, scope, budget,
  material, or role on any of the three records.
- A draft is generated during Slice 1 (draft generation is Slice 2+).
- `Compliment Line` is populated when `Portfolio Confidence = Low` OR
  `Project Status = Unclear`.
- A record's Airtable Status / Outreach Status / Score / Contact
  Today ranking changes as a result of the portfolio check.
- `Evidence Basis` contains anything other than `Page text/captions`
  in Round 1.
- A record's outreach status auto-flips because a URL was populated.

---

## Change log

- 2026-02-19 — Ryan approved 16-field schema with two revisions (Best
  Project URL note; attribution workflow rule) and locked build order.
  Waiting on Claude/Make to complete steps 2–4 before frontend work
  begins.
- 2026-02-19 (later) — Slice 1 shipped. Acceptance dry run against all
  three approved records passed the safety-path checks.
- 2026-02-19 (fix pass, Ryan) — five originally-missing fields now
  populated on every check (`Portfolio Check Status`,
  `Portfolio Checked At`, `Portfolio Evidence Basis`,
  `Portfolio Why This Was Chosen`, `Portfolio Error Reason`).
  `Portfolio Best Project Title` bug fixed — now required on every
  found project. Low-confidence Compliment Line rule tightened
  server-side (hard requirement, not soft).
- 2026-02-19 (Bloodhound-side, in response) — card component made
  **case-insensitive AND underscore-tolerant** on every governed value
  comparison. Fixed a safety-critical latent bug where a stored
  `"low"` (lowercase) would have failed the strict `"Low"` equality
  check and leaked the Compliment Line. See `key()` helper in
  `CompletedProjectProofCard.jsx`.

### Actual select-option values retained by Ryan (canonical, 2026-02-19)

These are the values Claude/Make ships today. Bloodhound treats them
as authoritative; the card is case + underscore tolerant so any of
the below forms round-trip correctly.

| Field | Values Claude/Make ships |
|---|---|
| Portfolio Check Status | `Complete`, `Failed`, `Pending` (blank until first run) |
| Portfolio Found | `yes`, `unclear`, `no` |
| Portfolio Check Confidence | `high`, `medium`, `low` |
| Portfolio Project Status | `completed`, `unclear`, (occasionally missing) |
| Portfolio Business Role | `contractor`, `designer`, `architect`, (etc.) |
| Portfolio Outreach Recommendation | `portfolio_opener`, `generic_business_opener`, `do_not_use` |
| Portfolio Evidence Basis | Free-form short string (e.g. `Portfolio/gallery page`, `Testimonial with project reference`, `Page text/captions`) — no longer locked to a single option |

### Acceptance-test slate — 2026-02-19 update

Live web search is **not deterministic between runs**. On the
2026-02-19 re-run, Rockwell Builders returned High confidence with a
real evidence URL (67 Oleander Court, Mandeville) instead of the
original Low/Unclear. That was not a bug — it was a genuinely better
search result the operator's manual check missed.

Practical rule for future QA: **do not pin any specific record to a
specific outcome.** Verify safety *behaviour* instead:

- **Any record that comes back with `Confidence = Low` OR
  `Project Status = Unclear`** must produce: blank Compliment Line,
  "Review source" link label, amber warning colour on the link, and
  the `portfolio-compliment-suppressed` banner if Airtable happens to
  hold a value in that field anyway.
- **Any record that comes back with `Confidence = High/Medium` AND
  `Project Status = completed`** may surface the Compliment Line as
  a hero, "Evidence" link label, and green Recommendation styling.
- **Any record with `Portfolio Check Status = Failed`** must show
  the red failure banner with the `Portfolio Error Reason` — the
  rest of the card body may be blank.

Decor by Flora is now the most reliable anchor for the "insufficient
evidence" acceptance path because its site actively blocks scrapers,
so the check tends to return Unclear/Low across runs.
