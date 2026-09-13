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
    rate-limits us so the FastAPI layer can pass it through."""

    def __init__(self, message: str, status_code: int = 503,
                 retry_after: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


# The three research features Ryan asked for. Each carries the
# system-prompt fragment that shapes Perplexity's answer for its
# specific use case.
_SYSTEMS = {
    "decision_maker": (
        "You are a lead-research assistant helping a New Orleans contractor "
        "identify decision makers at businesses and properties. Given the "
        "lead context, answer WHO runs this business or owns this property, "
        "their role (owner/GM/manager), and any verified contact leads. "
        "Ground every claim in a cited web source with a date when possible. "
        "If evidence is thin, say so — do not invent names. Reply in "
        "plain-text short paragraphs, no markdown."
    ),
    "permit_explainer": (
        "You are a lead-research assistant helping a New Orleans contractor "
        "read building/renovation permits. Given a permit description, "
        "explain in plain English what work the permit covers, typical "
        "scope and duration for that permit type, and any red flags (e.g. "
        "structural changes, historic-district review). Cite New Orleans "
        "municipal sources where possible. Do not invent code sections. "
        "Reply in plain-text short paragraphs, no markdown."
    ),
    "landlord_background": (
        "You are a lead-research assistant helping a New Orleans contractor "
        "vet rental-property owners for turnover-work outreach. Given the "
        "owner name and address, surface public records: LLC filings, "
        "additional properties they own in NOLA (rough count is fine), "
        "any news mentions, and how large their portfolio appears. Cite "
        "sources. Do not invent portfolio counts. Reply in plain-text short "
        "paragraphs, no markdown."
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
        self._client = Perplexity(api_key=api_key)  # type: ignore
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
            # Try to extract a meaningful status without leaking the key
            status = getattr(e, "status_code", None) or 502
            retry_after = None
            resp_obj = getattr(e, "response", None)
            if resp_obj is not None:
                try:
                    retry_after = resp_obj.headers.get("retry-after")
                except Exception:  # noqa: BLE001
                    pass
            msg = str(e)[:240]
            # Never echo the API key even if the SDK included it in the message
            msg = msg.replace(os.environ.get("PERPLEXITY_API_KEY", ""), "***")
            if status == 401:
                raise PerplexityError(
                    "Perplexity authentication failed — rotate the key in "
                    "the console and update PERPLEXITY_API_KEY.",
                    status_code=401,
                ) from e
            if status == 429:
                raise PerplexityError(
                    "Perplexity rate limit reached — try again shortly.",
                    status_code=429,
                    retry_after=retry_after,
                ) from e
            log.warning("Perplexity call failed: %s", msg)
            raise PerplexityError(
                f"Perplexity request failed: {msg}", status_code=502,
            ) from e

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
