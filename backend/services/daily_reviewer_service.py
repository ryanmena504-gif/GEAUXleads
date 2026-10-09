"""Daily lead reviewer — backend version (no Make scenario needed).

Every morning, scans leads for genuinely new info (new permits, projects,
contact changes), flags them via the three New info fields, and auto-runs
the portfolio check on at most 3 per day. Everything else appears in the
Fresh Intel digest for Ryan to tap.

Design (from blueprint):
- Skip already-flagged leads (no duplicate work)
- Skip contacted/dead leads (reviewer handles the research bottleneck)
- Max 25 leads scanned per run
- Max 3 auto-enhancements per day — hard cap
- Nothing reaches a lead without Ryan's tap
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MAX_SCAN_PER_RUN = 25
MAX_AUTO_ENHANCE_PER_DAY = 3

REVIEW_PROMPT = """You are reviewing a lead for new information.

Lead details:
{business_info}

Existing summary on record:
{existing_summary}

Search for genuinely NEW information about this business: new permits filed,
new completed projects, new locations, changed phone/email/website, new key
people. Compare against the existing summary above.

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
    try:
        result = await research_async("general", prompt)
        text = (result.get("answer") or result.get("summary") or "").strip()
        if not text or "NOTHING_NEW" in text.upper():
            return None
        return text[:500]
    except Exception:
        log.exception("daily reviewer: research failed for %s", opp.get("id"))
        return None


async def run_daily_review(
    svc,
    auto_enhance_fn=None,
    max_scan: int = MAX_SCAN_PER_RUN,
    max_enhance: int = MAX_AUTO_ENHANCE_PER_DAY,
) -> Dict[str, Any]:
    """Run one daily review pass. Returns stats."""
    all_opps = await svc.list()
    eligible = [o for o in all_opps if _is_eligible(o)][:max_scan]

    flagged = 0
    enhanced = 0
    today = datetime.now(timezone.utc).date().isoformat()

    for opp in eligible:
        opp_id = opp.get("id")
        summary = await _check_for_new_info(opp)
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

    return {
        "scanned": len(eligible),
        "flagged": flagged,
        "auto_enhanced": enhanced,
        "cap": max_enhance,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
