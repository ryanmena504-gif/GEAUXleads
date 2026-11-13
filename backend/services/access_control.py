"""Shared password for the website, and the separate morning-job secret.

APP_PASSWORD is the lock on every API route except the two health checks.
If it is missing, those routes refuse to answer. That is deliberate: an
unset password must not leave the lead list open.

WEBHOOK_CRON_SECRET is the extra key the morning research job sends.
The phone password alone cannot start that job.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

APP_PASSWORD_ENV = "APP_PASSWORD"
CRON_SECRET_ENV = "WEBHOOK_CRON_SECRET"
APP_PASSWORD_HEADER = "x-app-password"
CRON_SECRET_HEADER = "x-cron-secret"
# EventSource cannot set a header. Only the live-update stream accepts this.
STREAM_QUERY_PARAM = "access_key"

OPEN_PATHS = frozenset({"/api/health", "/api/health/deep"})
# Twilio cannot send the app password. These POST routes skip it and check
# X-Twilio-Signature (signed with TWILIO_AUTH_TOKEN) themselves instead.
TWILIO_SIGNED_PATHS = frozenset({"/api/twilio/voice/missed-call"})

PASSWORD_NOT_CONFIGURED = {
    "ok": False,
    "error": "password_not_configured",
    "detail": (
        "The site is locked because APP_PASSWORD is not set on the API. "
        "In Render, open the API service, go to Environment, and add "
        "APP_PASSWORD with a password you choose. Save, wait for the "
        "redeploy, then type that same password in the app. "
        "The steps are in docs/RENDER_SETUP.md. "
        "/api/health stays open while this is unset."
    ),
}

CRON_SECRET_NOT_CONFIGURED = {
    "ok": False,
    "error": "cron_secret_not_configured",
    "detail": (
        "WEBHOOK_CRON_SECRET is not set on the API, so the morning "
        "research job will not run. Add it in the API service's "
        "Environment in Render, and put the same value on the cron job. "
        "See docs/RENDER_SETUP.md."
    ),
}


def secret_equal(supplied: str, expected: str) -> bool:
    """True when the two strings match. Length differences do not raise."""
    if not supplied or not expected:
        return False
    left = hashlib.sha256(supplied.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


def app_password() -> str:
    return (os.environ.get(APP_PASSWORD_ENV) or "").strip()


def cron_secret() -> str:
    return (os.environ.get(CRON_SECRET_ENV) or "").strip()


def presented_app_password(headers, query, path: str) -> str:
    """Password the caller sent, if any.

    The header is the normal path. A bearer token is accepted so a plain
    HTTP client can send Authorization. The query string is accepted only
    on the live-update stream, which cannot set a header.
    """
    direct = (headers.get(APP_PASSWORD_HEADER) or "").strip()
    if direct:
        return direct
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return token
    if path.rstrip("/") == "/api/live/stream":
        return (query.get(STREAM_QUERY_PARAM) or "").strip()
    return ""


def password_failure(supplied: str) -> Optional[dict]:
    """None when the password is configured and matches.

    A missing server password is a 503 setup problem, not a wrong guess.
    """
    expected = app_password()
    if not expected:
        return PASSWORD_NOT_CONFIGURED
    if not secret_equal(supplied, expected):
        return {
            "ok": False,
            "error": "unauthorized",
            "detail": "Sign in required.",
        }
    return None


def cron_failure(supplied: Optional[str]) -> Optional[dict]:
    """None when the morning-job secret is configured and matches."""
    expected = cron_secret()
    if not expected:
        return CRON_SECRET_NOT_CONFIGURED
    if not secret_equal((supplied or "").strip(), expected):
        return {
            "ok": False,
            "error": "unauthorized",
            "detail": "The morning job secret does not match.",
        }
    return None


def is_open_path(path: str) -> bool:
    return path.rstrip("/") in OPEN_PATHS


def is_twilio_signed_path(path: str) -> bool:
    return path.rstrip("/") in TWILIO_SIGNED_PATHS
