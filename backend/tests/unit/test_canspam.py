"""Cold emails carry an opt-out line and a postal address from the environment."""
import os

from services.canspam import ADDRESS_PLACEHOLDER, business_mailing_address, ensure_canspam


def test_missing_env_uses_a_placeholder_and_not_a_street(monkeypatch):
    monkeypatch.delenv("BUSINESS_MAILING_ADDRESS", raising=False)
    assert business_mailing_address() == ADDRESS_PLACEHOLDER
    body = ensure_canspam("Hi Ada, I do showers.")
    assert 'reply "unsubscribe"' in body
    assert "The Shirtless Handyman" in body
    assert ADDRESS_PLACEHOLDER in body
    assert "Magazine" not in body
    assert "70115" not in body


def test_env_address_is_used_and_the_footer_is_not_doubled(monkeypatch):
    monkeypatch.setenv("BUSINESS_MAILING_ADDRESS", "PO Box 100\nNew Orleans, LA 70112")
    once = ensure_canspam("Hi Ada.")
    assert "PO Box 100" in once
    twice = ensure_canspam(once)
    assert twice == once
    assert twice.lower().count('reply "unsubscribe"') == 1


def test_empty_env_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("BUSINESS_MAILING_ADDRESS", "   ")
    assert os.environ["BUSINESS_MAILING_ADDRESS"].strip() == ""
    assert business_mailing_address() == ADDRESS_PLACEHOLDER
