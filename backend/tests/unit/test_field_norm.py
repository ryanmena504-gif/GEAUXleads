import pytest

from services import field_norm as fn


@pytest.mark.parametrize("value", [
    "504-231-8890",
    "(504) 231-8890",
    "+1 504 231 8890",
    "15042318890",
])
def test_valid_phones_normalize_to_the_same_digits(value):
    assert fn.is_valid_phone(value)
    assert fn.phone_digits(value) == "5042318890"


@pytest.mark.parametrize("value", [
    None, "", "n/a", "unknown",
    "555-1234",           # 7 digits
    "0000000000",         # single repeated digit
    "5555555555",
    "104-231-8890",       # NANP forbids 0/1 leading the area code
    "504-131-8890",       # ...or leading the exchange
])
def test_unusable_phones_are_rejected(value):
    assert not fn.is_valid_phone(value)


def test_email_is_extracted_from_surrounding_text():
    assert fn.normalize_email("Marie Ashby <Marie@Ashby.NET> (personal)") == "marie@ashby.net"


@pytest.mark.parametrize("value", [
    "owner@example.com", "noreply@roofing.com", "do-not-reply@x.org", "yourname@site.com",
])
def test_placeholder_emails_parse_but_are_not_deliverable(value):
    assert fn.normalize_email(value) is not None
    assert not fn.is_valid_email(value)


def test_address_requires_a_street_line_not_just_a_city():
    assert fn.has_address({"address": "1428 Prytania St"})
    assert not fn.has_address({"address": "New Orleans"})
    assert not fn.has_address({"address": None})


def test_address_normalization_collapses_spelling_variants():
    a = fn.normalize_address("1234 St. Charles Avenue, Apt 2")
    b = fn.normalize_address("1234 saint charles ave apt 2")
    assert a == b


def test_coerce_number_distinguishes_absent_from_zero():
    assert fn.coerce_number(None) is None
    assert fn.coerce_number("") is None
    assert fn.coerce_number("n/a") is None
    assert fn.coerce_number("not priced") is None
    assert fn.coerce_number(0) == 0.0
    assert fn.coerce_number("$48,500") == 48500.0


def test_coerce_number_ignores_booleans():
    # An Airtable checkbox must never be summed as 1 into a money total.
    assert fn.coerce_number(True) is None
    assert fn.coerce_number(False) is None


def test_permit_normalization_rejects_status_words():
    assert fn.normalize_permit("RNVS-24-01882") == "RNVS2401882"
    assert fn.normalize_permit("pending") is None
    assert fn.normalize_permit("N/A") is None


def test_as_list_splits_free_text_multiselects():
    assert fn.as_list("stale, unverified") == ["stale", "unverified"]
    assert fn.as_list(["a", "", None]) == ["a"]
    assert fn.as_list(None) == []
