# RESTORE.md — merge the best of both versions

**Goal:** MERGE, don't overwrite. The Railway app keeps its newer pages and gets back the
parts that worked on the Emergent version (https://hound-priorities.emergent.host, captured
Sep 25, 2026). **Do not delete, hide, or replace any existing Railway page, feature, or
component.** If two things conflict, stop and ask Ryan which one wins.

Tip: this repo was exported from Emergent, so the missing pieces are probably still in git
history. Check `git log` before rebuilding anything from scratch.

## A. KEEP — Railway pages Ryan likes (don't remove or redesign)

- **Today's Missions** (`/missions`): missions grouped by action (Send Text, etc.) and priority,
  with Done / Snooze.
- **People to Know** (`/relationships`): partner cards with Why this matters, Public project
  connection, What to do next, Website / Public record links, Follow Up Email.
- **Projects to Watch** (`/intelligence`): non-permit signals with What's happening / Why it
  may fit / What to do next, platform filter.

Keep them in the sidebar.

## B. BRING BACK from Emergent

1. **Home "work list"**: the four stat tiles (Ready / Needs enrichment / Fresh / Follow-ups
   today), the **Today's brief** card with follow-ups due ("Email nudge · X days since last
   email"), and the four sections in order: **Ready to Contact → Contacted → All Projects →
   Cold — Needs Enrichment** (collapsed). The sections are driven by the Airtable `Current Queue`
   / `Contact Readiness` fields. As of Sep 25 the counts were 1 / 13 / 5 / 75 out of 94.
2. **Real Estate Agents section**: reads Airtable table `Real Estate Agent Outreach`
   (`tblN0rwhbZiXYKp3T`).
3. **Landlords section**: reads Airtable table `Landlords` (`tblMdDhLKk1fbpVeZ`). Show Portfolio
   Size and Turnover Cadence.
4. **Discovery** (`/discovery/property-managers`): back in the nav.
5. **Agent buttons on the lead detail page** (`/opportunities/:id`). Both run in Make.com; the
   app just POSTs `{"record_id": "<Airtable Leads record id>"}` and then re-fetches the record:
   - **Run Portfolio Check** → `https://hook.us2.make.com/rti29k0s786ash6osoxq2t5ycksmv2uc`
     (fills the `Portfolio …` fields).
   - **Write Outreach Draft** → `https://hook.us2.make.com/c3bp5ey44t1l05v5vcwmc895ql8utd6g`
     (fills `Draft Outreach Subject` / `Draft Outreach Body`).
   Put the URLs in backend env vars (`PORTFOLIO_CHECK_WEBHOOK`, `OUTREACH_WRITER_WEBHOOK`) and
   call them from the backend, not the browser. Show "Working…" while waiting. Neither agent
   sends anything. Test each on one lead before calling it done.

## C. FIX on the Railway pages (display bugs seen Sep 25)

- **People to Know** shows "High priority" and "Not a fit" on the same card (Greige, Backyard
  Living). Pick one rule: if fit is "Not a fit", don't show a priority badge.
- **Projects to Watch** shows a "Ready to contact" badge on public signals, while the card itself
  says the signal "is not permission to contact". Remove that badge from signal cards. These are
  watch-only.
- **Today's Missions** says "0 of 82," and contacted partners show as "Need more info · CONTACT
  TBD." Missions should exclude Contacted records unless a follow-up is due, and use the same
  queue fields as Home, so the two pages never disagree.
- Brand: the sidebar says "Bloodhound · Owner-operated project book." Change it to
  **GEAUXleads** (Emergent already did).

## D. Rules that must hold

- Nothing sends automatically. Buttons only open drafts for Ryan to send himself.
- First-contact actions only in Ready to Contact. Contacted gets follow-up only. Everything
  else gets none. Gate: `outreachAllowed()` (`frontend/src/lib/queue.js`) + `outreach_policy.py`.
- Real Airtable values only; missing money → "Not estimated yet."

## E. Done means

- [ ] Every page in A still works and looks the same, except for the fixes in C.
- [ ] Everything in B is present and working on desktop and mobile.
- [ ] Home counts match Airtable.
- [ ] Both agent buttons tested on one real lead each.
- [ ] Error boundaries on every route; a failed API call shows an error, not "no results."
- [ ] Short summary for Ryan listing anything that couldn't be done, and why.
