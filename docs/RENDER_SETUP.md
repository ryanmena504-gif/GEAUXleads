# What to set in Render after this update

The site refuses every lead, draft, research call, and send until `APP_PASSWORD` is set. That is on purpose. `/api/health` still answers, so a lock is not a crash.

Do these in order. You can do steps 1–3 before you merge, which avoids a locked morning.

## 1. Put a password on the API

1. Open [dashboard.render.com](https://dashboard.render.com).
2. Open the **API** service. It is the one whose address is `https://geauxleads.onrender.com`. It is not the website service.
3. Click **Environment** in the left menu.
4. Click **Add Environment Variable**.
5. Name: `APP_PASSWORD`
6. Value: a password you make up. Use a long one, and write it down somewhere only you have. This is the password the phone will ask for.
7. Click **Save Changes**. Render will redeploy the API. Wait until the deploy is live.

## 2. Set the morning-job secret on the same API

1. Still in that API service, **Environment**.
2. If `WEBHOOK_CRON_SECRET` is already there, leave the value alone and copy it somewhere temporary. You will paste it onto the cron job in step 6.
3. If it is missing, add it. Name: `WEBHOOK_CRON_SECRET`. Value: a second long random string, different from the password. Save.

## 3. Confirm the public address

On the same Environment page, `PUBLIC_BACKEND_URL` should be:

`https://geauxleads.onrender.com`

No `/api` on the end, no trailing slash required. If it is missing, add it and save.

## 4. Merge, then sign in on the phone

1. Merge the pull request. Wait until the API deploy finishes.
2. Open the website.
3. Type the same `APP_PASSWORD`. The phone remembers it.
4. If the page lists the Render steps instead of a password box, step 1 did not land. Add `APP_PASSWORD` and wait for the redeploy. You are not locked out of the server. The site is waiting for that variable.

Signing out is in Settings: **Sign out of this phone**.

## 5. Check the API plan

1. On the API service, open **Settings**.
2. Look at the instance type.
3. If it says **Free**, change it to the smallest always-on plan (Starter, about $7 a month). Free goes to sleep after 15 quiet minutes, and it blocks the port the one-press Gmail send uses.
4. If it already says Starter or anything larger, leave it.

The website (static site) can stay on the free static plan.

## 6. Create the morning research job

The job wakes every hour and does nothing unless it is 7am in New Orleans. That keeps daylight saving time from moving it. It researches at most 10 leads. It does not send email. A failed paid lookup is not retried.

Render → **New** → **Cron Job**:

1. Connect this repo and use the `main` branch after the merge.
2. Name: `geauxleads-morning-research`
3. Runtime: Python
4. Build command: `python --version`
5. Start command: `python backend/scripts/morning_enrichment.py`
6. Schedule: `0 * * * *`
7. Instance: the smallest one. Render's minimum for a cron job is about $1 a month.
8. Environment variables, same values as the API:
   - `APP_PASSWORD`
   - `WEBHOOK_CRON_SECRET`
   - `PUBLIC_BACKEND_URL` = `https://geauxleads.onrender.com`
9. Create the job.

`render.yaml` in the repo describes this same cron and nothing else. You can use **New Blueprint** instead of the clicks above. If Render offers to change or recreate the existing website or API, cancel and use the clicks. Fill the three variables when it asks. They are not stored in the file.

## 7. Turn off the old in-website timer

If the API environment has `ENRICHMENT_AUTO_ENABLED`, delete it. The website no longer reads it. Leaving it set does nothing, but deleting it avoids confusion.

The 25-lead Fresh Intel scan is not on a schedule. Leave it that way.

## 8. Airtable plan

Open Airtable → the workspace billing page.

- If the plan is **Free**, move to **Team** (about $20 a month for one person, billed yearly). Free allows 1,000 API calls a month for the whole workspace, and both this app and Make spend from that pile.
- If it is already Team, do nothing.
- Do not buy Business for this.

## 9. Make, when you have a minute

This update does not change Make. In the scenarios that run after a lead already exists, stop them from clearing contact name, phone, email, owner, mailing address, confidence, and the date the contact was checked. Keep the scenario that creates a new row. The clicks are in `docs/MAKE_FIXES.md`.

## If the morning email used to fire on its own

The old schedule file from the previous host was not running on Render, and it has been removed. The morning-email address still exists (`POST /api/cron/morning-brief`). It now needs both headers:

- `X-App-Password`: the same value as `APP_PASSWORD`
- `X-Cron-Secret`: the same value as `WEBHOOK_CRON_SECRET`

The **send the brief now** button in Settings works once you are signed in. It does not need the cron secret.
