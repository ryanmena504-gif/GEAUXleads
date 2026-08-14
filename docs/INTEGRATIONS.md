# Integration boundaries

## Messaging dispatch — not connected

**This application does not send messages.** Approving a lead writes
`Approval status` and `Outreach status` on the Airtable record and nothing else.
No SMS, email, or webhook leaves the process.

This is stated explicitly because the UI wording ("Approve & Send") reads as if
it dispatches, and an operator who believes a message went out will behave
differently from one who knows it did not. The approve response carries the
disclaimer verbatim:

```json
{
  "state": "approved",
  "note": "Approved — no message has been sent. Dispatch is not yet connected; see docs/INTEGRATIONS.md."
}
```

Downstream delivery, if it happens, is a Make.com scenario watching the
`Approval status` column. That scenario is outside this repository.

## The contract a future dispatcher must honour

When dispatch is wired up — here or in Make — it must satisfy the following.
The pieces are already in place; only the send call is missing.

### 1. Idempotency key

Every dispatch takes an idempotency key. `POST /api/leads/{id}/action` accepts
`idempotency_key` in the body; when omitted, the server derives one:

```
idem_<sha256(action:entity_id:YYYY-MM-DD)[:32]>
```

Scoped to the UTC day, so an operator double-click or a retried webhook is a
replay, while a deliberate re-approval tomorrow is a new decision. A replayed key
returns the stored response with `"replayed": true` and performs **no** write.

`revert_approval` invalidates the key so a lead can be deliberately re-approved
the same day.

The store (`IdempotencyStore` in `backend/services/audit.py`) is a bounded
in-process LRU. **It does not survive a restart and is not shared across
workers.** Before real messages are sent, replace it with a shared
implementation — Redis, or an Airtable table keyed on the idempotency key. The
interface is three methods (`get`, `put`, `invalidate`); no call site changes.

Until then the deployment must stay single-worker, or duplicate dispatch is
possible across workers.

### 2. Server-side eligibility, re-checked at dispatch time

`services.outreach_policy.evaluate()` is the single source of truth. It is
enforced in the service layer, not the route layer, so no write path can skip it.
A dispatcher must call it again immediately before sending — the record may have
changed between approval and dispatch.

Blocked writes raise `OutreachBlocked`, which the API returns as HTTP **409** with
the full structured verdict:

```json
{
  "error": "outreach_blocked",
  "eligibility": {
    "eligible": false,
    "score": 35,
    "score_source": "computed_from_live_fields",
    "blockers": [{"code": "no_verified_contact", "message": "...", "remediation": "..."}],
    "warnings": [],
    "checks": [],
    "recipient": {},
    "thresholds": {}
  }
}
```

409 rather than 400: the request is well-formed; it is the record's current
state that forbids it.

### 3. Audit event

Every decision writes an `AuditEvent` (`backend/services/audit.py`) with the
policy verdict **as it stood at decision time**. Re-deriving the verdict on read
would rewrite history, so it is captured, not recomputed.

Outcomes: `accepted`, `rejected`, `error`, `replayed`.

The default sink is a 500-event in-memory ring buffer plus one structured log
line per event:

```
audit {"action": "approve", "entity_id": "rec...", "outcome": "accepted", ...}
```

The log line survives a restart; the buffer does not. `GET /api/audit/events`
reads the buffer and reports `"durable": false` so a caller cannot mistake an
empty response for "nothing happened".

For a durable trail, implement `AuditSink.write` (a one-method Protocol) against
Airtable, Postgres, or S3 and pass it to `AuditLog(sink=...)`. No call site
changes.

### 4. Consent and suppression

`do_not_contact` must be checked at dispatch time, not only at approval time. It
is already a blocking check in the policy (`marked_do_not_contact`).

### 5. Duplicate suppression

Only the canonical member of a duplicate group is actionable. Approving a
non-canonical record is blocked (`duplicate_lead`). A dispatcher iterating over
records directly rather than through the service layer must apply
`services.aggregations.canonical_only()` itself, or it will message the same
person twice.

## Airtable

- **Read**: full table via a 45-second TTL cache, with up to 3 retries and
  stale-serve on failure. Under Airtable's ~5 rps per-base limit.
- **Write**: strict per-service allowlist, enforced against the live schema.
  Formula, rollup, lookup, and system fields are rejected even if allowlisted.
- **Never**: create, rename, retype, or delete a field or table.

Reverting an approval degrades through a list of plausible single-select values
(`Pending`, `Pending Approval`, `Needs Review`, `Not Approved`, then clearing the
cell), because Airtable rejects a single-select value that is not a configured
option. The response reports which one took via `reverted_to`.

## Interactions / activity history

There is no interactions table. The activity timeline is synthesised from real
timestamps already on the record (`created_time`, `validated_at`,
`message_generated_at`, `message_sent_date`, `date_replied`). No history is
fabricated. Adding a real interactions table would not change the read contract.

## Relationships and Intelligence pages

Static illustrative content, not derived from any data source. They are labelled
as previews in the UI and excluded from every decision path. See
`frontend/src/components/PreviewNotice.jsx`.
