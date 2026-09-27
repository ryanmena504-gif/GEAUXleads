"""
Twilio Lookup v2 wrapper. Read-only phone-number intelligence — carrier,
line type (mobile / landline / VoIP / etc.), and caller name when the
number has a CNAM record.

Never sends messages. Never places calls. This module is the ENTIRE
Twilio surface Bloodhound talks to, in line with the app's founding
rule that all outbound communication stays as native `sms:` / `mailto:`
handoff.

Feature-flagged: when TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are absent
or blank, the service constructor returns None and callers surface a
clean 503. No import-time crash, no worker restart loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("bloodhound.twilio_lookup")

try:
    from twilio.rest import Client  # type: ignore
    from twilio.base.exceptions import TwilioRestException  # type: ignore
    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    Client = None  # type: ignore
    TwilioRestException = Exception  # type: ignore
    _SDK_AVAILABLE = False


class TwilioLookupError(Exception):
    """Application-level Twilio error with an HTTP status hint."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


# Fields we request from Lookup v2. Cost per fetch (as of Feb 2026):
#   line_type_intelligence = ~$0.005 (carrier + line type)
#   caller_name            = ~$0.01  (US only, CNAM)
# Total ~$0.015 per lookup. Cheap enough that Ryan can hit every
# unknown inbound number.
_LOOKUP_FIELDS = "line_type_intelligence,caller_name"


class TwilioLookupService:
    """Thin wrapper over `twilio.rest.Client.lookups.v2.phone_numbers`.

    Public surface:
        lookup(phone_number) -> dict
    """

    def __init__(self, account_sid: str, auth_token: str):
        if not _SDK_AVAILABLE:
            raise RuntimeError(
                "twilio package is not installed — run `pip install twilio`"
            )
        self._client = Client(account_sid, auth_token)  # type: ignore

    def lookup(self, phone_number: str) -> Dict[str, Any]:
        phone_number = (phone_number or "").strip()
        if not phone_number:
            raise TwilioLookupError("phone_number is required", status_code=400)
        try:
            res = self._client.lookups.v2.phone_numbers(phone_number).fetch(
                fields=_LOOKUP_FIELDS,
            )
        except TwilioRestException as e:  # type: ignore
            status = int(getattr(e, "status", 502) or 502)
            code = getattr(e, "code", None)
            msg = getattr(e, "msg", None) or str(e)
            # 20404 = "not found" (unallocated number). 60600 = invalid.
            if status == 404 or code in (20404,):
                raise TwilioLookupError(
                    f"Twilio doesn't recognize {phone_number}",
                    status_code=404,
                ) from e
            if status in (401, 403):
                raise TwilioLookupError(
                    "Twilio auth failed — rotate TWILIO_AUTH_TOKEN.",
                    status_code=401,
                ) from e
            if status == 429:
                raise TwilioLookupError(
                    "Twilio rate limit reached — try again shortly.",
                    status_code=429,
                ) from e
            log.warning("Twilio Lookup failed for %s: %s", phone_number, msg[:200])
            raise TwilioLookupError(
                f"Twilio Lookup failed: {msg[:200]}", status_code=502,
            ) from e
        except Exception as e:  # noqa: BLE001
            log.exception("Unexpected Twilio Lookup error for %s", phone_number)
            raise TwilioLookupError(
                f"Unexpected error: {str(e)[:200]}", status_code=502,
            ) from e

        # Normalize the response shape so the frontend gets a stable
        # contract even if Twilio adds/removes fields.
        lti = getattr(res, "line_type_intelligence", None) or {}
        cname = getattr(res, "caller_name", None) or {}
        return {
            "phone_number": getattr(res, "phone_number", phone_number),
            "national_format": getattr(res, "national_format", None),
            "country_code": getattr(res, "country_code", None),
            "valid": getattr(res, "valid", None),
            # line type intelligence
            "line_type": lti.get("type") if isinstance(lti, dict) else None,
            "carrier_name": lti.get("carrier_name") if isinstance(lti, dict) else None,
            "mobile_country_code": lti.get("mobile_country_code") if isinstance(lti, dict) else None,
            "mobile_network_code": lti.get("mobile_network_code") if isinstance(lti, dict) else None,
            "error_code": lti.get("error_code") if isinstance(lti, dict) else None,
            # caller name (CNAM — US only)
            "caller_name": cname.get("caller_name") if isinstance(cname, dict) else None,
            "caller_type": cname.get("caller_type") if isinstance(cname, dict) else None,
            # provenance
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


_service_singleton: Optional[TwilioLookupService] = None
_service_init_error: Optional[str] = None


def get_twilio_lookup_service() -> Optional[TwilioLookupService]:
    """Lazy singleton. None when creds are missing so callers 503 cleanly."""
    global _service_singleton, _service_init_error
    if _service_singleton is not None:
        return _service_singleton
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        _service_init_error = "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not configured"
        return None
    if not sid.startswith("AC"):
        _service_init_error = "TWILIO_ACCOUNT_SID must start with 'AC'"
        return None
    try:
        _service_singleton = TwilioLookupService(account_sid=sid, auth_token=token)
        _service_init_error = None
        return _service_singleton
    except Exception as e:  # noqa: BLE001
        _service_init_error = str(e)[:200]
        log.exception("Twilio Lookup service init failed")
        return None


def twilio_lookup_config_error() -> Optional[str]:
    return _service_init_error


async def lookup_async(phone_number: str) -> Dict[str, Any]:
    """Run the blocking SDK call in a worker thread so we don't stall
    the FastAPI event loop."""
    svc = get_twilio_lookup_service()
    if not svc:
        raise TwilioLookupError(
            twilio_lookup_config_error() or "Twilio Lookup is not configured",
            status_code=503,
        )
    return await asyncio.to_thread(svc.lookup, phone_number)
