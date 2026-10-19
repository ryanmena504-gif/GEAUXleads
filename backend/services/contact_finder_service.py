"""In-app Contact Finder — replaces the Make webhook scenario.

One tap on "Find contact" runs owner-contact research directly:
Perplexity identifies the property owner and finds publicly listed
contact info, then the result is written back to the lead's Airtable
record. No webhook, no Make, no JSON-module mapping to break.

Research only — nothing is ever sent to the lead.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# Sentinels the research prompt uses for "couldn't find it". These become
# None so we never write the literal text "none found" into Airtable.
_NOT_FOUND = {"none found", "unknown", "n/a", "not found", "none", ""}


def build_query(opp: Dict[str, Any]) -> str:
    """Build the research query from the opportunity's known fields."""
    address = opp.get("project_address") or opp.get("address")
    name = opp.get("name")
    company = opp.get("company")
    parts = []
    if address:
        parts.append(f"Property address: {address}")
    if name:
        parts.append(f"Lead name: {name}")
    if company:
        parts.append(f"Company on file: {company}")
    return "\n".join(parts) if parts else "No address or name on file."


def _clean(value: Any) -> Optional[str]:
    """Normalize a research result value: sentinels become None."""
    if value is None:
        return None
    s = str(value).strip().strip("\"'")
    if s.lower() in _NOT_FOUND:
        return None
    return s or None


def parse_result(answer: str) -> Dict[str, Optional[str]]:
    """Parse the research JSON robustly.

    The prompt asks for a bare JSON object, but models sometimes wrap it
    in markdown fences or add surrounding text. We try, in order:
    1. Direct json.loads of the whole answer.
    2. Strip ```json / ``` fences, then json.loads.
    3. Extract the substring from the first '{' to the last '}' and parse.
    Anything unparseable yields all-None (no partial writes of garbage).
    """
    text = (answer or "").strip()
    candidates = [text]

    # Strip markdown code fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())

    # Extract the outermost JSON object.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    data: Dict[str, Any] = {}
    for cand in candidates:
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                data = parsed
                break
        except (json.JSONDecodeError, ValueError):
            continue

    return {
        "owner_name": _clean(data.get("owner_name")),
        "phone": _clean(data.get("phone")),
        "email": _clean(data.get("email")),
        "entity_context": _clean(data.get("entity_context")),
    }


async def run_contact_finder(opp: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Run owner-contact research for one opportunity.

    Returns {owner_name, phone, email, entity_context} with None for
    anything not found. Raises PerplexityError (or RuntimeError) when
    research itself is unavailable — the caller maps that to a 503.
    """
    from services.perplexity_service import research_async

    query = build_query(opp)
    log.info("Contact Finder: researching %s", query.split("\n")[0][:80])
    result = await research_async("contact_finder", query)
    answer = result.get("answer") or result.get("output_text") or ""
    parsed = parse_result(answer)
    log.info(
        "Contact Finder: owner=%s phone=%s email=%s",
        bool(parsed["owner_name"]),
        bool(parsed["phone"]),
        bool(parsed["email"]),
    )
    return parsed
