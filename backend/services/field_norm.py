"""Normalization and syntactic validation of Airtable-sourced field values.

Everything downstream (eligibility, dedupe, ingestion diagnostics) reads fields
through these helpers so that a single definition of "this lead has a usable
phone number" exists in the codebase.

These are *syntactic* validators. They answer "could this value plausibly be
dialled / mailed / matched", not "does this endpoint exist". Nothing here
performs network calls.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, List, Optional

# Deliberately permissive: Airtable free-text columns hold values such as
# "user@example.com (personal)". We extract rather than reject.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Values operators type into Airtable to mean "nothing here".
_NULL_TOKENS = {
    "", "-", "--", "—", "n/a", "na", "none", "null", "unknown", "tbd",
    "not found", "not available", "no", "pending", "?",
}

# Substrings that make an email non-deliverable for outreach purposes even
# though it parses. Kept short and specific.
_PLACEHOLDER_EMAIL_TOKENS = (
    "example.com", "example.org", "test.com", "noreply", "no-reply",
    "donotreply", "do-not-reply", "email@", "yourname@", "info@example",
)

# North American numbering plan: 10 digits, or 11 leading with country code 1.
_NANP_LEN = 10


def is_blank(value: Any) -> bool:
    """True when the value carries no information."""
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    return str(value).strip().lower() in _NULL_TOKENS


def clean_text(value: Any) -> Optional[str]:
    """Collapse whitespace and map operator null-tokens to None."""
    if is_blank(value):
        return None
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if not is_blank(v)), None)
        if value is None:
            return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def first_present(record: dict, keys: Iterable[str]) -> Optional[str]:
    """First non-blank cleaned value across an ordered list of keys."""
    for key in keys:
        cleaned = clean_text(record.get(key))
        if cleaned:
            return cleaned
    return None


# ---------------------------------------------------------------- phone
def phone_digits(value: Any) -> Optional[str]:
    """Digits of a phone number, normalized to NANP national form."""
    cleaned = clean_text(value)
    if not cleaned:
        return None
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def is_valid_phone(value: Any) -> bool:
    """A dialable NANP number: 10 digits, valid area/exchange prefix."""
    digits = phone_digits(value)
    if not digits or len(digits) != _NANP_LEN:
        return False
    if len(set(digits)) == 1:  # 0000000000, 5555555555
        return False
    # NANP forbids 0/1 as the leading digit of the area code or the exchange.
    return digits[0] not in "01" and digits[3] not in "01"


def format_phone(value: Any) -> Optional[str]:
    digits = phone_digits(value)
    if not digits or len(digits) != _NANP_LEN:
        return clean_text(value)
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


# ---------------------------------------------------------------- email
def normalize_email(value: Any) -> Optional[str]:
    """Extract and lowercase the first email address embedded in the value."""
    cleaned = clean_text(value)
    if not cleaned:
        return None
    match = _EMAIL_RE.search(cleaned)
    return match.group(0).lower() if match else None


def is_valid_email(value: Any) -> bool:
    email = normalize_email(value)
    if not email:
        return False
    return not any(token in email for token in _PLACEHOLDER_EMAIL_TOKENS)


# ---------------------------------------------------------------- address
_STREET_SUFFIXES = {
    "street": "st", "st": "st", "avenue": "ave", "ave": "ave", "road": "rd",
    "rd": "rd", "boulevard": "blvd", "blvd": "blvd", "drive": "dr", "dr": "dr",
    "lane": "ln", "ln": "ln", "court": "ct", "ct": "ct", "place": "pl",
    "pl": "pl", "terrace": "ter", "ter": "ter", "circle": "cir", "cir": "cir",
    "highway": "hwy", "hwy": "hwy", "parkway": "pkwy", "pkwy": "pkwy",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}


def normalize_address(value: Any) -> Optional[str]:
    """Canonical address key: lowercased, punctuation-free, suffixes abbreviated.

    "1234 St. Charles Avenue, Apt 2" and "1234 saint charles ave apt 2" both
    reduce to the same key so dedupe can match them.
    """
    cleaned = clean_text(value)
    if not cleaned:
        return None
    text = cleaned.lower().replace("&", " and ")
    text = re.sub(r"\bsaint\b", "st", text)
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = [_STREET_SUFFIXES.get(t, t) for t in text.split() if t]
    return " ".join(tokens) or None


def has_address(record: dict, keys: Iterable[str] = ("address", "project_address")) -> bool:
    """An address is usable only when it carries a street line, not just a city."""
    raw = first_present(record, keys)
    if not raw:
        return False
    # A bare city name ("New Orleans") is not an address we can visit or mail.
    return bool(re.search(r"\d", raw)) and len(raw) >= 6


# ---------------------------------------------------------------- names
_ORG_SUFFIX_RE = re.compile(
    r"\b(llc|l\.l\.c|inc|incorporated|corp|corporation|co|company|ltd|"
    r"limited|plc|lp|llp|pllc|group|holdings)\b\.?"
)


def normalize_name(value: Any) -> Optional[str]:
    """Canonical person/business name key for dedupe matching."""
    cleaned = clean_text(value)
    if not cleaned:
        return None
    text = cleaned.lower()
    text = _ORG_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split()) or None


def normalize_permit(value: Any) -> Optional[str]:
    """Permit numbers vary in punctuation between sources; strip to alnum."""
    cleaned = clean_text(value)
    if not cleaned:
        return None
    key = re.sub(r"[^A-Za-z0-9]", "", cleaned).upper()
    # Guard against a permit column holding a status word rather than a number.
    return key if len(key) >= 4 and any(c.isdigit() for c in key) else None


# ---------------------------------------------------------------- numbers
def coerce_number(value: Any) -> Optional[float]:
    """Parse Airtable currency/number cells that may arrive as text or lists.

    Returns None for genuinely absent values so callers can distinguish
    "no estimate recorded" from "estimated at $0".
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if v not in (None, "")), None)
        if value is None:
            return None
        return coerce_number(value)
    cleaned = clean_text(value)
    if not cleaned:
        return None
    stripped = re.sub(r"[^\d.\-]", "", cleaned.replace(",", ""))
    if stripped in ("", "-", ".", "-."):
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def coerce_int_or_float(value: Any) -> Optional[float | int]:
    """coerce_number, collapsed to int when the value is whole."""
    number = coerce_number(value)
    if number is None:
        return None
    return int(number) if float(number).is_integer() else number


def as_list(value: Any) -> List[Any]:
    """Coerce Airtable multi-select / free-text values to a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if not is_blank(v)]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return [value]


def contains_token(value: Any, tokens: Iterable[str]) -> bool:
    """Case-insensitive substring match against a value of any Airtable type."""
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_token(v, tokens) for v in value)
    haystack = str(value).lower()
    return any(token in haystack for token in tokens)
