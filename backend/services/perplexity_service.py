"""
Perplexity research service — wraps the Perplexity Agent API for on-demand
lead research inside Bloodhound.

Design rules baked in:
  - API key is read ONLY from PERPLEXITY_API_KEY at service init; never
    accepted from a request body, never logged, never returned to the
    frontend.
  - Feature-flagged: if the env var is missing the service constructor
    returns None and every research route returns a clean 503 — the rest
    of the app keeps working.
  - Uses the official `perplexity` SDK. Preset defaults to `medium`
    (bundles a mid-cost web-grounded model + web_search tool). The
    system prompt forces grounded, dated answers with uncertainty
    disclosure — the classifier next door owns opinions; Perplexity's
    job here is to fetch evidence.
  - Results are cached in MongoDB by (research_type, record_id) so a
    second tap on the same "Who runs this?" button is free.
  - Errors are converted to typed exceptions so the FastAPI layer can
    map them to 401 / 429 / 503 without leaking the key or a stacktrace.
    The conversion classifies by exception type (connection vs timeout
    vs HTTP status) instead of collapsing everything into one generic
    "request failed". The SDK is constructed with max_retries=0, so a
    connection error has not been retried — it is logged once and the
    caller moves on.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bloodhound.perplexity")

# Import lazily so a missing SDK never crashes the worker; the service
# constructor surfaces the real ImportError.
try:
    from perplexity import Perplexity  # type: ignore
    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    Perplexity = None  # type: ignore
    _SDK_AVAILABLE = False


class PerplexityError(Exception):
    """Application-level error with an HTTP status hint. `retry_after`
    carries the upstream Retry-After header verbatim when Perplexity
    rate-limits us so the FastAPI layer can pass it through. `error_kind`
    names the failure in plain terms ("connection", "timeout", "auth",
    "forbidden", "rate_limit", "bad_request", "upstream") so callers can
    write a human-readable note about it instead of a raw SDK message."""

    def __init__(self, message: str, status_code: int = 503,
                 retry_after: Optional[str] = None,
                 error_kind: str = "upstream"):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.error_kind = error_kind


# Fail fast instead of hanging on the SDK's long default timeout: a hung
# Perplexity call should surface as a clear timeout, not stall the
# background task for minutes.
_REQUEST_TIMEOUT_SECS = 120.0


def _redact(text: str) -> str:
    """Strip the API key from a message if it ever appears in one.
    (Guard the empty-key case: replacing "" would mangle every string.)"""
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    return text.replace(key, "***") if key else text


def _upstream_detail(exc: Exception) -> str:
    """Short upstream detail for logs: the error message from Perplexity's
    response body when the SDK carried one."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:160]
        if isinstance(err, str):
            return err[:160]
    return ""


def _classify_error(exc: Exception) -> PerplexityError:
    """Turn an SDK / transport exception into a typed PerplexityError with
    a plain-English message and an error_kind callers can render.

    Classification is by exception class name + status_code, not by
    importing SDK error classes, so it works with the real SDK
    (APIConnectionError, APITimeoutError, APIStatusError, ...) and with
    fakes in tests. Never echoes the API key, even if the SDK put it in
    the message.
    """
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    retry_after = None
    resp_obj = getattr(exc, "response", None)
    if resp_obj is not None:
        try:
            retry_after = resp_obj.headers.get("retry-after")
        except Exception:  # noqa: BLE001
            pass
    raw = _redact(str(exc)[:240])
    detail = _upstream_detail(exc)

    if "Timeout" in name:
        return PerplexityError(
            "Perplexity took too long to answer (over 2 minutes) — "
            "try again shortly.",
            status_code=503, error_kind="timeout",
        )
    if "ConnectionError" in name or "ConnectError" in name:
        return PerplexityError(
            "Could not reach Perplexity at all — the request never got an "
            "answer (connection error). This is not a key or credit problem; "
            "the app's route to Perplexity failed. Try again later; if it "
            "keeps happening, the connection needs a look.",
            status_code=503, error_kind="connection",
        )
    if status == 401:
        return PerplexityError(
            "Perplexity authentication failed — rotate the key in "
            "the console and update PERPLEXITY_API_KEY.",
            status_code=401, error_kind="auth",
        )
    if status == 403:
        return PerplexityError(
            "Perplexity refused this key for the Agent API (HTTP 403) — "
            "the key may not have Agent API access, or the account may be "
            "restricted. Check the key's permissions in the Perplexity "
            "console; re-pasting the same key will not help.",
            status_code=403, error_kind="forbidden",
        )
    if status == 429:
        return PerplexityError(
            "Perplexity rate limit reached — try again shortly.",
            status_code=429, retry_after=retry_after,
            error_kind="rate_limit",
        )
    if status == 400:
        suffix = f": {detail}" if detail else ""
        return PerplexityError(
            f"Perplexity rejected the request (HTTP 400){suffix}",
            status_code=400, error_kind="bad_request",
        )
    if isinstance(status, int) and status >= 500:
        suffix = f": {detail}" if detail else ""
        return PerplexityError(
            f"Perplexity's own service failed (HTTP {status}){suffix} — "
            "try again shortly.",
            status_code=502, error_kind="upstream",
        )
    log.warning(
        "Perplexity call failed: kind=upstream status=%s type=%s msg=%s detail=%s",
        status, name, raw, detail,
    )
    return PerplexityError(
        f"Perplexity request failed: {raw or 'unknown error'}",
        status_code=status if isinstance(status, int) else 502,
        retry_after=retry_after, error_kind="upstream",
    )


# Shared context every research prompt below carries: who Ryan is, what
# winning looks like, and what counts as a real lead. The individual
# prompts used to say only "a New Orleans contractor" — the research came
# back generic and bathroom-centric, and nothing said what the answer was
# for. Keep this prefix short: it is instruction text, not answer text,
# so it does not disturb the strict output formats some prompts demand
# (bare JSON for contact_finder, PHONE:/EMAIL: lines for owner_contact).
_TRADE_PREFIX = (
    "Context: you are researching for The Shirtless Handyman — Ryan Mena, "
    "a microcement and Venetian plaster specialist in New Orleans, NOT a "
    "general handyman. His rule is 'surface to coat': floors, walls, "
    "countertops, showers, wet rooms — a bathroom is never required. He "
    "never spot-repairs failed microcement and never gives a firm price on "
    "the phone. The goal is replies, then booked in-person estimates, then "
    "won jobs — finding a name is only the feeder. "
    "Real-lead screen: only treat a lead as real when the person and the "
    "property are verifiable and the ask is coherent. Flag instead of "
    "passing on overpayment, forwarding money to a third party, printed or "
    "emailed checks, or requests for payee forms or bank details. "
)

# The research features Ryan asked for. Each carries the
# system-prompt fragment that shapes Perplexity's answer for its
# specific use case.
_SYSTEMS = {
    "decision_maker": (
        _TRADE_PREFIX
        + "You are a lead-research assistant helping Ryan "
        "identify decision makers at businesses and properties. Given the "
        "lead context, answer WHO runs this business or owns this property, "
        "their role (owner/GM/manager), and any verified contact leads. "
        "Ground every claim in a cited web source with a date when possible. "
        "If evidence is thin, say so — do not invent names. Reply in "
        "plain-text short paragraphs, no markdown. End with one final line "
        "and nothing after it, exactly in this form: "
        "DECISION_MAKER: <full name, or unknown>. "
        "That line is a name only — no title, no sentence, no URL."
    ),
    "permit_explainer": (
        _TRADE_PREFIX
        + "You are a lead-research assistant helping Ryan "
        "read building/renovation permits. Given a permit description, "
        "explain in plain English what work the permit covers, typical "
        "scope and duration for that permit type, and any red flags (e.g. "
        "structural changes, historic-district review). Cite New Orleans "
        "municipal sources where possible. Do not invent code sections. "
        "Reply in plain-text short paragraphs, no markdown."
    ),
    "landlord_background": (
        _TRADE_PREFIX
        + "You are a lead-research assistant helping Ryan "
        "vet rental-property owners whose units may need seamless finishes "
        "between tenants. Given the "
        "owner name and address, surface public records: LLC filings, "
        "additional properties they own in NOLA (rough count is fine), "
        "any news mentions, and how large their portfolio appears. Cite "
        "sources. Do not invent portfolio counts. Reply in plain-text short "
        "paragraphs, no markdown."
    ),
    "re_agent_background": (
        _TRADE_PREFIX
        + "You are a lead-research assistant helping Ryan "
        "target real estate agents for a 'seamless, photo-ready surfaces "
        "before the listing hits MLS' pitch. Given the agent's name and brokerage, "
        "surface: verified public business email + phone (from the "
        "brokerage's site, agent's own site, or Realtor.com/Zillow profile "
        "— NEVER a personal-looking number), recent NOLA listings and "
        "approximate 12-month sold volume, brokerage tenure, and whether "
        "they specialize in flips / historic renos / higher-end listings. "
        "Prioritize any signal that they list homes where dated surfaces — "
        "bathrooms, kitchens, living rooms — would drag the price. Cite every source URL. If a phone or email cannot "
        "be verified from a public business source, say so — do not "
        "invent contact details. Reply in plain-text short paragraphs, "
        "no markdown."
    ),
    "owner_contact": (
        _TRADE_PREFIX
        + "You are a contact-research assistant helping Ryan "
        "reach property owners about renovation work. Given the owner's name "
        "and the property address, find any PUBLICLY LISTED phone number or "
        "email address for that owner. Check: Orleans Parish assessor records, "
        "Louisiana Secretary of State business filings (for LLC-owned property "
        "report the registered agent's contact), the owner's own business "
        "website, and public directories. Start your reply with exactly these "
        "four lines:\n"
        "PHONE: <the number, or 'none found'>\n"
        "EMAIL: <the address, or 'none found'>\n"
        "NAME: <the owner's name, or 'none found'>\n"
        "MAILING: <the assessor mailing address on one line, or 'none found'>\n"
        "Then 2-4 short plain-text paragraphs: what you found, which source "
        "each contact came from, and your confidence the owner was correctly "
        "matched. If the owner cannot be confidently matched to a public "
        "record, say so and report none found. NEVER invent a phone number "
        "or email address. No markdown."
    ),
    "contact_finder": (
        _TRADE_PREFIX
        + "You are a contact-research assistant helping Ryan "
        "find property owners and their public contact info. Given a property "
        "address and any known lead name or company, do two things: (1) identify "
        "the property owner (person or LLC — check Orleans Parish assessor "
        "records, Louisiana Secretary of State filings), (2) find any PUBLICLY "
        "LISTED phone number or email for that owner (business website, public "
        "directories, registered-agent filings). "
        "Reply with ONLY a JSON object, no markdown fences, no other text, "
        "with exactly these keys: "
        '{"owner_name": "<owner or decision maker, or \'unknown\'>", '
        '"phone": "<phone number, or \'none found\'>", '
        '"email": "<email address, or \'none found\'>", '
        '"mailing_address": "<mailing address, or \'none found\'>", '
        '"contact_source": "<homeowner or business>", '
        '"source_url": "<one https URL for the contact, or \'none found\'>", '
        '"confidence": "<High, Medium, or Low>", '
        '"entity_context": "<2-3 sentences: what you found, which source each '
        "contact came from, and why the owner match is or isn't confident>\"}. "
        "contact_source is homeowner when the owner is a person, and business "
        "when the owner is a company or LLC. "
        "NEVER invent a phone number, email, name, or mailing address. If the "
        "owner cannot be confidently matched, use 'unknown' / 'none found'."
    ),
    "homeowner_lookup": (
        _TRADE_PREFIX
        + "You are looking up the owner of a residential property in the "
        "New Orleans area for Ryan. Use public records only: the permit, "
        "the Orleans Parish assessor (owner of record and mailing address), "
        "and Louisiana Secretary of State filings when the owner is an LLC. "
        "Return the owner's name, the mailing address on the assessor or "
        "tax roll, and a phone or email only when it is publicly listed. "
        "contact_source is homeowner when the owner is a person, and "
        "business when the owner is a company or LLC. "
        "Reply with ONLY a JSON object, no markdown fences, no other text, "
        "with exactly these keys: "
        '{"owner_name": "<owner name, or \'unknown\'>", '
        '"phone": "<phone number, or \'none found\'>", '
        '"email": "<email address, or \'none found\'>", '
        '"mailing_address": "<mailing address on one line, or \'none found\'>", '
        '"contact_source": "<homeowner or business>", '
        '"source_url": "<one https URL for the record you used, or \'none found\'>", '
        '"confidence": "<High, Medium, or Low>", '
        '"entity_context": "<2-3 sentences: which record, what it shows, and '
        "how sure you are the owner matches this address>\"}. "
        "NEVER invent a phone number, email, name, or mailing address."
    ),
    # The daily reviewer (Fresh Intel picker) calls research_async("general")
    # with its own review prompt as the query. This type did not exist until
    # now: every reviewer check raised "Unknown research_type 'general'",
    # was swallowed, and returned nothing — the picker could never flag
    # anything. Do not remove this entry without updating
    # daily_reviewer_service.py.
    "general": (
        _TRADE_PREFIX
        + "You are reviewing a lead for genuinely NEW information. Only "
        "report news that matters to Ryan's trade: new permits or projects "
        "involving a surface to coat (floors, walls, countertops, showers, "
        "wet rooms — a bathroom is never required), new locations, changed "
        "phone/email/website, or new key people. Do NOT flag permits for "
        "pure plumbing, electrical, or roofing work with no surface to "
        "coat. Ground every claim in a cited web source with a date when "
        "possible. If evidence is thin, say so — do not invent facts. "
        "Reply in plain-text short paragraphs, no markdown."
    ),
}


class PerplexityResearchService:
    """Thin wrapper over `client.responses.create` for the Agent API.

    Public surface:
        research(research_type, query) -> dict
    """

    def __init__(self, api_key: str, preset: str = "medium"):
        if not _SDK_AVAILABLE:
            raise RuntimeError(
                "perplexityai package is not installed — run "
                "`pip install perplexityai`"
            )
        # Explicit timeout so a hung call fails fast as a clear timeout
        # instead of stalling for the SDK's long default. No custom
        # base_url: the SDK default (https://api.perplexity.ai) is the
        # right endpoint.
        # max_retries=0: the SDK default is 2, and a retried call spends
        # another credit. A timeout or connection error is logged once
        # and the lead is marked Research failed. Ryan can tap again.
        self._client = Perplexity(  # type: ignore
            api_key=api_key,
            timeout=_REQUEST_TIMEOUT_SECS,
            max_retries=0,
        )
        self._preset = preset

    def research(self, research_type: str, query: str) -> Dict[str, Any]:
        system = _SYSTEMS.get(research_type)
        if not system:
            raise PerplexityError(
                f"Unknown research_type '{research_type}'", status_code=400
            )
        query = (query or "").strip()
        if not query:
            raise PerplexityError("query must be non-empty", status_code=400)
        if len(query) > 4000:
            raise PerplexityError("query too long (>4000 chars)", status_code=400)

        try:
            # OpenAI-compatible "responses" surface — the SDK alias for
            # the Agent API. `instructions` carries the system prompt;
            # `input` is the user query as a plain string. A `preset`
            # bundles a web-grounded model + tools (web_search, etc.)
            # so we don't have to name a Router model directly.
            # `output_text` is the convenience joined-text property.
            resp = self._client.responses.create(
                preset=self._preset,
                instructions=system,
                input=query,
            )
        except Exception as e:  # noqa: BLE001
            # Classify instead of collapsing: callers need to tell a
            # connection failure apart from an auth / rate-limit / upstream
            # failure, in plain English, on the lead itself.
            err = _classify_error(e)
            log.warning(
                "Perplexity call failed: kind=%s status=%s type=%s msg=%s",
                err.error_kind, err.status_code, type(e).__name__,
                _redact(str(e)[:240]),
            )
            raise err from e

        # Extract answer + sources without depending on SDK version quirks.
        answer = getattr(resp, "output_text", None) or ""
        if not answer:
            # Fall back to walking `output` for any text content.
            output = getattr(resp, "output", None) or []
            parts: List[str] = []
            for item in output:
                content = getattr(item, "content", None) or []
                for c in content:
                    text = getattr(c, "text", None)
                    if text:
                        parts.append(text)
            answer = "\n\n".join(parts).strip()

        # Sources: on the Agent API, web-search hits live inside
        # `output[i].results[]` on items whose `.type == "search_results"`.
        # `output[i].annotations` may also carry per-citation URLs on
        # some builds. Walk both, dedupe by URL, cap at 10.
        sources: List[Dict[str, str]] = []
        seen = set()
        output = getattr(resp, "output", None) or []
        for item in output:
            item_type = getattr(item, "type", None)
            # search_results items — the primary citation source.
            results = getattr(item, "results", None) or []
            for r in results:
                url = getattr(r, "url", None) or (r.get("url") if isinstance(r, dict) else None)
                if not url or url in seen:
                    continue
                title = (
                    getattr(r, "title", None)
                    or (r.get("title") if isinstance(r, dict) else None)
                    or url
                )
                sources.append({"title": title, "url": url})
                seen.add(url)
            # Some SDK builds also park inline citations on content annotations.
            content = getattr(item, "content", None) or []
            for c in content:
                for a in getattr(c, "annotations", None) or []:
                    url = getattr(a, "url", None)
                    if url and url not in seen:
                        sources.append({"title": getattr(a, "title", None) or url, "url": url})
                        seen.add(url)
            if len(sources) >= 10:
                break
        sources = sources[:10]

        usage = getattr(resp, "usage", None)
        usage_dict: Optional[Dict[str, Any]] = None
        if usage is not None:
            usage_dict = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }

        return {
            "research_type": research_type,
            "answer": answer or "(no answer returned)",
            "sources": sources,
            "model": getattr(resp, "model", None) or f"preset:{self._preset}",
            "usage": usage_dict,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


_service_singleton: Optional[PerplexityResearchService] = None
_service_init_error: Optional[str] = None


def get_perplexity_service() -> Optional[PerplexityResearchService]:
    """Lazy singleton. Returns None when the key is missing so callers
    can render a clean 503."""
    global _service_singleton, _service_init_error
    if _service_singleton is not None:
        return _service_singleton
    key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not key or not key.startswith("pplx-"):
        _service_init_error = "PERPLEXITY_API_KEY not configured"
        return None
    try:
        _service_singleton = PerplexityResearchService(api_key=key)
        _service_init_error = None
        return _service_singleton
    except Exception as e:  # noqa: BLE001
        _service_init_error = str(e)[:200]
        log.exception("Perplexity service init failed")
        return None


def perplexity_config_error() -> Optional[str]:
    return _service_init_error


async def research_async(research_type: str, query: str) -> Dict[str, Any]:
    """Run Perplexity's blocking SDK call in a worker thread so we don't
    stall the FastAPI event loop."""
    svc = get_perplexity_service()
    if not svc:
        raise PerplexityError(
            perplexity_config_error() or "Perplexity is not configured",
            status_code=503,
        )
    return await asyncio.to_thread(svc.research, research_type, query)
