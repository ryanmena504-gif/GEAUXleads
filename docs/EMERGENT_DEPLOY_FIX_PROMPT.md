# Emergent deploy fix prompt

Paste everything below the line into Emergent.

---

## PROMPT (copy from here)

Bloodhound live site https://hound-priorities.emergent.host is broken. Fix deployment + Airtable connection. Do not redesign the UI. Do not reconnect Resend. Do not add paid tools. Do not auto-send messages.

### What’s wrong (already diagnosed)
1. Live frontend is an OLD Aug 12 build (“Contact Now / Watch / Not a Fit”). GitHub live branch is newer and different (“People to contact today / Projects to watch / People to know”).
2. `/api/health` returns `backend: "sample"` even though `airtable_enabled: true` — Airtable init is failing and the app fell back to sample data.
3. `/api/opportunities` returns HTTP 500, so Today lists are empty. Summary/top still work. Root cause on the old build: sample `.list()` rejects the `sort=` kwarg the API passes.

### Required source of truth
Use GitHub branch: `computer/simplified-relationship-flow`

That branch already includes:
- PR #3 — NBA Hunt exclusion, Contact Ready gate, dashboard status
- PR for harden list / Airtable init error surfacing (merge if open): branch `cursor/harden-opportunities-list-f6e6`

If Emergent workspace code does not match that GitHub branch, pull/sync from GitHub `computer/simplified-relationship-flow` first. Do NOT deploy the old “Contact Now” cleanup workspace.

### What you must do
1. Sync Emergent workspace to GitHub `computer/simplified-relationship-flow` (latest).
2. Confirm env vars in Emergent (Secrets / env):
   - `AIRTABLE_ENABLED=true`
   - `AIRTABLE_API_KEY` = valid personal access token with `data.records:read`, `data.records:write`, `schema.bases:read`
   - `AIRTABLE_BASE_ID` = the real Bloodhound base id
   - `AIRTABLE_OPPORTUNITIES_TABLE=Leads`
   - `AIRTABLE_LEADS_TABLE=Leads`
3. Restart backend after env changes.
4. Save to GitHub if Emergent asks.
5. Deploy → Deploy Now → `hound-priorities.emergent.host`
6. Wait for the new build to finish.

### Verify after deploy (must all pass)
- `GET /api/health` → `"backend":"airtable"` and count > 0 (not sample)
- `GET /api/config` → `airtable_enabled: true`, `airtable_init_error: null`
- `GET /api/opportunities` → HTTP 200 and a non-empty JSON array
- `GET /api/leads/next-best-action` → not the “Leads service not available” note
- Today page shows real leads, NOT “Source: Sample data”
- Today section labels are “People to contact today / Projects to watch / People to know” (not Contact Now / Not a Fit)

### If Airtable still falls back to sample
Read `airtable_init_error` from `/api/config` and fix the reported credential/base/table problem. Do not invent new Airtable columns. Do not change Make scenarios.

### Out of scope
- No Resend / Twilio / auto-send
- No paid enrichment tools
- No merge from `main` or intelligence branches
- No Airtable schema redesign / annual revenue fields

When done, reply with: deploy URL, `/api/health` JSON, `/api/config` JSON, and a screenshot of Today with real data.
