"""Perplexity error classification.

Guards the fix for the silent Contact Finder failure (Oct 30, 2026):
a connection error reaching Perplexity must come back as kind
"connection" with a plain-English message — never collapsed into a
generic 502 "request failed" that hides whether the key, the credits,
or the route is the problem. Classification is by exception class name
+ status_code, so these tests use fakes and never touch the network or
the real SDK.
"""
import os

import pytest

from services.perplexity_service import PerplexityError, _classify_error


class _FakeConnectionError(Exception):
    """Stands in for perplexity.APIConnectionError ("Connection error.")."""


class _FakeTimeoutError(Exception):
    """Stands in for perplexity.APITimeoutError."""


class _FakeStatusError(Exception):
    """Stands in for perplexity.APIStatusError and friends."""

    def __init__(self, message, status_code, body=None, headers=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.response = _FakeResponse(headers or {})


class _FakeResponse:
    def __init__(self, headers):
        self.headers = headers


def test_connection_error_is_kind_connection_not_502_generic():
    err = _classify_error(_FakeConnectionError("Connection error."))
    assert err.error_kind == "connection"
    assert err.status_code == 503
    assert "not a key or credit problem" in str(err)


def test_timeout_error_is_kind_timeout():
    err = _classify_error(_FakeTimeoutError("Request timed out."))
    assert err.error_kind == "timeout"
    assert err.status_code == 503
    assert "too long" in str(err)


def test_401_stays_auth():
    err = _classify_error(_FakeStatusError("invalid_api_key", 401))
    assert err.error_kind == "auth"
    assert err.status_code == 401


def test_403_is_forbidden_not_auth():
    err = _classify_error(_FakeStatusError("restricted_api_key", 403))
    assert err.error_kind == "forbidden"
    assert err.status_code == 403
    assert "re-pasting the same key will not help" in str(err)


def test_429_keeps_retry_after():
    err = _classify_error(
        _FakeStatusError("slow down", 429, headers={"retry-after": "30"})
    )
    assert err.error_kind == "rate_limit"
    assert err.status_code == 429
    assert err.retry_after == "30"


def test_500_upstream_carries_body_detail():
    err = _classify_error(
        _FakeStatusError(
            "boom", 500, body={"error": {"message": "upstream boom"}}
        )
    )
    assert err.error_kind == "upstream"
    assert "upstream boom" in str(err)


def test_generic_exception_falls_back_to_upstream_502():
    err = _classify_error(Exception("something weird"))
    assert err.error_kind == "upstream"
    assert err.status_code == 502
    assert "something weird" in str(err)


def test_api_key_is_never_echoed(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-SECRET123")
    err = _classify_error(Exception("bad key pplx-SECRET123 in message"))
    assert "pplx-SECRET123" not in str(err)
    assert "***" in str(err)


def test_perplexity_error_carries_kind():
    err = PerplexityError("x", status_code=503, error_kind="connection")
    assert err.error_kind == "connection"
    assert err.status_code == 503
