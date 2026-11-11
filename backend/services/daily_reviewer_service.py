"""Daily lead reviewer — backend version (no Make scenario needed).

Every morning, scans leads for genuinely new info (new permits, projects,
contact changes), flags them via the three New info fields, and auto-runs
the portfolio check on at most 3 per day. Everything else appears in the
Fresh Intel digest for Ryan to tap.

End goal: turn strangers into booked estimates — success is replies, then
booked in-person estimates, then won jobs. Flagging fresh info is only the
feeder; a lead that never replies is not a win. Only flag news that could
move a real surface job one step closer to a reply.

Design (from blueprint):
- Skip already-flagged leads (no duplicate work)
- Skip contacted/dead leads (reviewer handles the research bottleneck)
- Max 25 leads scanned per run
- Max 3 auto-enhancements per day — hard cap
- Nothing reaches a lead without Ryan's tap
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MAX_SCAN_PER_RUN = 25
MAX_AUTO_ENHANCE_PER_DAY = 3

REVIEW_PROMPT = """You are reviewing a lead for new information for The Shirtless Handyman — Ryan Mena, a microcement and Venetian plaster specialist in New Orleans (NOT a general handyman). His rule is "surface to coat": floors, walls, countertops, showers, wet rooms — a bathroom is never required.

Lead details:
{business_info}

Existing summary on record:
{existing_summary}

Search for genuinely NEW information about this business: new permits filed,
new completed projects, new locations, changed phone/email/website, new key
people. Compare against the existing summary above. Only flag news that could move a real surface job one step closer to a reply — replies, then booked in-person estimates, are the goal; finding is only the feeder.

Do NOT flag permits for pure plumbing, electrical, or roofing work with no surface to coat. Real-lead screen: if the new information looks like a scam pattern (overpayment, forwarding money to a third party, printed or emailed checks, requests for payee forms or bank details), do not flag it as a lead — report it in one sentence starting with "SCAM PATTERN:" instead.

Report ONLY genuinely new information in 1-2 plain-English sentences.
If nothing new, output exactly: NOTHING_NEW
"""


def _is_eligible(opp: Dict[str, Any]) -> bool:
    """Skip already-flagged, contacted, or dead leads."""
    if opp.get("flag_new_info"):
        return False
    status = (opp.get("status") or "").lower()
    if status in ("dead", "do_not_contact", "contacted", "sent"):
        return False
    return True


async def _check_for_new_info(opp: Dict[str, Any]) -> Optional[str]:
    """Use Perplexity to check for new info. Returns summary or None."""
    from services.perplexity_service import research_async

    business_info = "\n".join(
        f"{k}: {v}"
        for k, v in {
            "Business": opp.get("name"),
            "Company": opp.get("company"),
            "Website": opp.get("website"),
            "Address": opp.get("project_address"),
        }.items()
        if v
    )
    if not business_info.strip():
        return None

    prompt = REVIEW_PROMPT.format(
        business_info=business_info,
        existing_summary=opp.get("evidence_summary") or opp.get("ai_summary") or "(none)",
    )
    # A failed paid call raises. The batch loop counts it and does not
    # call research_async again for this lead.
    result = await research_async("general", prompt)
    text = (result.get("answer") or result.get("summary") or "").strip()
    if not text or "NOTHING_NEW" in text.upper():
        return None
    return text[:500]


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    return value


async def run_daily_review(
    svc,
    auto_enhance_fn=None,
    max_scan: int = MAX_SCAN_PER_RUN,
    max_enhance: int = MAX_AUTO_ENHANCE_PER_DAY,
) -> Dict[str, Any]:
    """Run one daily review pass. Returns stats.

    `svc.list` is synchronous on the live service. Awaiting it used to
    raise TypeError before a single lead was scanned. Paid research
    calls are not retried: three failures in a row stop the pass.
    """
    all_opps = await _maybe_await(svc.list())
    eligible = [o for o in all_opps if _is_eligible(o)][:max_scan]

    flagged = 0
    enhanced = 0
    failures = 0
    stopped_early = False
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        failure_limit = max(1, int(os.environ.get("ENRICHMENT_MAX_CONSECUTIVE_FAILURES", "3")))
    except ValueError:
        failure_limit = 3

    for opp in eligible:
        if failures >= failure_limit:
            stopped_early = True
            break
        opp_id = opp.get("id")
        try:
            summary = await _check_for_new_info(opp)
        except Exception as exc:
            failures += 1
            # Type name only. The SDK message can echo request details, and
            # a paid-call failure is not retried from this log line.
            log.warning(
                "daily reviewer: research failed for %s (%s)",
                opp_id, type(exc).__name__,
            )
            continue
        failures = 0
        if not summary:
            continue

        # Flag it.
        try:
            svc.update_fields(opp_id, {
                "new_info_flag": True,
                "new_info_summary": summary,
                "new_info_date": today,
            })
            flagged += 1
        except Exception:
            log.exception("daily reviewer: flag failed for %s", opp_id)
            continue

        # Auto-enhance up to the cap.
        if enhanced < max_enhance and auto_enhance_fn:
            try:
                await auto_enhance_fn(opp_id)
                enhanced += 1
            except Exception:
                log.exception("daily reviewer: auto-enhance failed for %s", opp_id)

    if failures >= failure_limit:
        stopped_early = True
    return {
        "scanned": len(eligible),
        "flagged": flagged,
        "auto_enhanced": enhanced,
        "cap": max_enhance,
        "consecutive_failures": failures,
        "stopped_early": stopped_early,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
