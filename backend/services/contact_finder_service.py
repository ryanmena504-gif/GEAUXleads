"""In-app Contact Finder — replaces the Make webhook scenario.

One tap on "Find contact" runs owner-contact research directly:
Perplexity identifies the property owner and finds publicly listed
contact info, then the result is written back to the lead's Airtable
record. No webhook, no Make, no JSON-module mapping to break.

End goal: a found contact is only useful if it moves a real surface job
one step closer to a reply — replies, then booked in-person estimates,
then won jobs. A name with no verifiable person or property behind it is
not a lead. Real-lead screen: the research prompt flags overpayment,
forwarding money to a third party, printed/emailed checks, and payee or
bank-detail requests instead of treating them as contact leads.

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
    city = opp.get("city")
    if city:
        parts.append(f"City: {city}")
    if opp.get("permit_number"):
        parts.append(f"Permit number: {opp.get('permit_number')}")
    if opp.get("permit_description"):
        parts.append(f"Permit description: {opp.get('permit_description')}")
    if opp.get("project_type"):
        parts.append(f"Project type: {opp.get('project_type')}")
    if name:
        parts.append(f"Lead name: {name}")
    if company:
        parts.append(f"Company on file: {company}")
    if opp.get("owner"):
        parts.append(f"Owner on file: {opp.get('owner')}")
    if opp.get("decision_maker"):
        parts.append(f"Contact name on file: {opp.get('decision_maker')}")
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

    source = _clean(data.get("contact_source"))
    if source:
        source = source.lower()
        if "home" in source:
            source = "homeowner"
        elif "business" in source or "company" in source or "llc" in source:
            source = "business"
        else:
            source = None
    confidence = _clean(data.get("confidence"))
    if confidence:
        lowered = confidence.lower()
        confidence = {"high": "High", "medium": "Medium", "low": "Low"}.get(lowered)
    return {
        "owner_name": _clean(data.get("owner_name")),
        "phone": _clean(data.get("phone")),
        "email": _clean(data.get("email")),
        "mailing_address": _clean(data.get("mailing_address")),
        "contact_source": source,
        "source_url": _clean(data.get("source_url")),
        "confidence": confidence,
        "entity_context": _clean(data.get("entity_context")),
    }


async def run_contact_finder(opp: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Run owner-contact research for one opportunity.

    Residential permit leads use the homeowner lookup (assessor owner,
    mailing address, public phone/email). Everything else uses the
    business contact finder. One call either way — a failure is raised
    and not retried here.

    Returns owner_name, phone, email, mailing_address, contact_source,
    source_url, confidence, and entity_context. Missing pieces are None.
    """
    from services.contact_research import is_residential_permit
    from services.perplexity_service import research_async

    residential = is_residential_permit(opp)
    research_type = "homeowner_lookup" if residential else "contact_finder"
    query = build_query(opp)
    log.info("Contact Finder: %s %s", research_type, query.split("\n")[0][:80])
    result = await research_async(research_type, query)
    answer = result.get("answer") or result.get("output_text") or ""
    parsed = parse_result(answer)
    if not parsed.get("contact_source"):
        parsed["contact_source"] = "homeowner" if residential else "business"
    # The citation list is a fallback when the model omits source_url.
    if not parsed.get("source_url"):
        sources = result.get("sources") or []
        if sources and isinstance(sources[0], dict):
            parsed["source_url"] = sources[0].get("url")
    log.info(
        "Contact Finder: owner=%s phone=%s email=%s source=%s",
        bool(parsed["owner_name"]),
        bool(parsed["phone"]),
        bool(parsed["email"]),
        parsed.get("contact_source"),
    )
    return parsed
