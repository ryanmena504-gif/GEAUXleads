"""
Emergent-managed Resend email sender.

Owns the outbound send call and nothing else — the caller supplies subject,
recipient, and message. Never logs the API key.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import re
from html.parser import HTMLParser
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger("bloodhound.email")

# CONSTANT — never read from env so a missing platform-injected var can't break sends.
EMAIL_BASE_URL = "https://integrations.emergentagent.com"


# ---- Guardrail gate (from the Resend playbook) ------------------------------
# Best-effort structural defense-in-depth for G2 (credential harvesting) and
# G3 (link hygiene). Called on every send path. Never softened, never wrapped
# in try/except. If a legitimate email trips this, rewrite the copy instead.

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = (
    "reply with your password", "reply with the code", "send your password", "cvv",
    "send us your password", "enter your password below", "confirm your card number",
    "your full card number", "seed phrase", "recovery phrase", "verify your card",
    "social security number", "confirm your bank details",
)
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


class EmailSendError(Exception):
    """Raised when the outbound provider rejects the send. Carries the upstream
    HTTP status so the API layer can map to a graceful 4xx/5xx."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


async def send_outreach_email(
    *,
    recipient_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a single transactional email via the Emergent-managed Resend proxy.

    Every send routes through the guardrail gate first (G2 + G3 structural
    checks). Returns the provider response payload (includes `id` on success).
    Raises EmailSendError on any non-2xx.
    """
    _assert_safe_email(subject, html_body)

    key = os.environ.get("EMERGENT_EMAIL_KEY")
    from_name = os.environ.get("EMAIL_FROM_NAME")
    if not key:
        raise EmailSendError("EMERGENT_EMAIL_KEY missing from backend env", status_code=503)
    if not from_name:
        raise EmailSendError("EMAIL_FROM_NAME missing from backend env", status_code=503)

    payload: Dict[str, Any] = {
        "to": [recipient_email],
        "subject": subject,
        "html": html_body,
        "from_name": from_name,
    }
    if text_body:
        payload["text"] = text_body
    if reply_to:
        payload["contact_email"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": key},
                json=payload,
            )
        if resp.status_code >= 400:
            body_snippet = (resp.text or "")[:400]
            log.error("Resend send failed: %d %s", resp.status_code, body_snippet)
            raise EmailSendError(
                f"Provider rejected email ({resp.status_code}): {body_snippet}",
                status_code=resp.status_code,
            )
        try:
            data = resp.json()
        except Exception:
            data = {}
        return {"id": data.get("id"), "raw": data}
    except httpx.HTTPError as e:
        log.exception("Resend network error")
        raise EmailSendError(f"Email transport error: {e}", status_code=502) from e

