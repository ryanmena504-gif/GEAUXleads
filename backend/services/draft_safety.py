"""
Draft-safety guard — Python mirror of `frontend/src/lib/draftSafety.js`.

Prevents raw AI prompts, unfilled template placeholders, or empty machine
output from ever being treated as a ready-to-send outreach message. Used
by the audit endpoint that scans persisted Airtable message fields for
records where the composer would have produced garbage.

Keep patterns in sync with the JS version. Each pattern must be a strong
signal — false positives would flag legitimate outreach.
"""
from __future__ import annotations
import re
from typing import Optional, Tuple

# Prompt-shaped openings. Anchored to start of trimmed text.
_PROMPT_OPENERS = [
    re.compile(r"^you are (a |an |the )", re.I),
    re.compile(r"^you're (a |an |the )", re.I),
    re.compile(
        r"^please (enrich|pull|research|provide|generate|summarize|extract|analyze|classify|score)\b",
        re.I,
    ),
    re.compile(r"^i am (an? )?(ai|assistant|language model|claude|chatbot)\b", re.I),
    re.compile(r"^as an? (ai|assistant|language model)\b", re.I),
    re.compile(r"^\[(system|assistant|user|human|instructions?|prompt|role|task)\]", re.I),
    re.compile(
        r"^(system|assistant|user|human|instructions?|prompt|role|task)\s*[:—-]\s",
        re.I,
    ),
    re.compile(r"^###\s*(instructions?|role|task|context|prompt|system)", re.I),
    # Directive-to-operator openers — bare imperatives Claude uses to tell
    # Ryan what to do next. Live prod bug (2026-02-19) was "Build a short
    # finish-fit memo…" stored in `current_recommendation` and piped into
    # the mailto body.
    re.compile(
        r"^(build|map|monitor|verify|review|prepare|investigate|extract|scrape|"
        r"classify|tag|categorize|assess|score|rate|log)\s+"
        r"(a|an|the|it|this|that|these|those|recurring|any|all|for|from|to|through)\b",
        re.I,
    ),
    re.compile(r"^(wait for|check for|update|ensure|confirm) (a |the |any |all )", re.I),
]

# Structural markers anywhere in the text.
_STRUCTURAL_MARKERS = [
    re.compile(r"\{\{[^}]{1,80}\}\}"),
    re.compile(r"<<[A-Z_ ]{3,}>>"),
    re.compile(r"\bTODO\s*:\s*(fill|write|generate|complete|replace)", re.I),
    re.compile(r"\[(FILL|INSERT|REPLACE|TODO)\s*[^\]]*\]", re.I),
    re.compile(r"\b(as an ai|as a language model|i'?m claude|i am claude)\b", re.I),
    re.compile(r"\bopenai\s+(gpt|api)", re.I),
]

_MIN_WORD_CHARS = 3


def looks_like_ai_prompt(text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Returns (trip, reason). trip=True means the text is NOT safe to
    present as a ready-to-send draft."""
    if text is None:
        return True, "empty"
    s = str(text).strip()
    if not s:
        return True, "empty"
    word_chars = re.sub(r"[^A-Za-z0-9]", "", s)
    if len(word_chars) < _MIN_WORD_CHARS:
        return True, "too_short"
    for pat in _PROMPT_OPENERS:
        if pat.search(s):
            return True, "prompt_opener"
    for pat in _STRUCTURAL_MARKERS:
        if pat.search(s):
            return True, "structural_marker"
    return False, None


# ---------------------------------------------------------------------------
# Outreach-claim softening (2026-11-16 review). Mirrors `softenDraftClaims`
# in frontend/src/lib/draftSafety.js — keep the two in sync.
#
# Ryan can't promise microcement "goes over existing tile, no demo day"
# before he has inspected the tile. Every stored or generated draft runs
# through this before it is shown or sent, so the promise always reads as
# conditional.
# ---------------------------------------------------------------------------
TILE_CONDITIONAL = "often goes over existing tile once I've checked it's solid"

_TILE_CLAIMS = [
    # "goes right over existing tile, no demo day" / "goes over existing tile"
    re.compile(
        r"\b(?:it\s+)?goes\s+(?:right\s+)?over\s+(?:the\s+|your\s+)?existing\s+tile"
        r"(?:\s*(?:,|—|-|–)\s*(?:so\s+)?no\s+demo(?:\s+day)?)?",
        re.I,
    ),
    # "right over your existing tile" without "goes"
    re.compile(r"\bright\s+over\s+(?:the\s+|your\s+)?existing\s+tile", re.I),
]
_ALREADY_CONDITIONAL = re.compile(r"once i['’]ve checked it['’]s solid", re.I)
_LEFTOVER_NO_DEMO = re.compile(r"\s*(?:,|—|-|–)\s*no\s+demo\s+day\b", re.I)


def soften_draft_claims(text: Optional[str]) -> str:
    """Rewrite unconditional "over existing tile / no demo day" promises.
    Idempotent; safe on empty input."""
    if not text:
        return text or ""
    s = str(text)
    # Already conditional ("…once I've checked it's solid") → leave it alone.
    if _ALREADY_CONDITIONAL.search(s):
        return _LEFTOVER_NO_DEMO.sub("", s)
    for pat in _TILE_CLAIMS:
        s = pat.sub(TILE_CONDITIONAL, s, count=1) if pat.search(s) else s
        if TILE_CONDITIONAL in s:
            break
    return _LEFTOVER_NO_DEMO.sub("", s)


# Listing-agent drafts must not point at a seller's price cuts, days on
# market or motivation (2026-11-16 review: "Saw your Cohn listing, a 1939
# home cut $50,000 since September..."). A stored draft that does is not
# shown; the safe listing-agent template is used instead.
_LISTING_PRESSURE = [
    re.compile(r"\$\s?\d[\d,]*k?\s+(?:in\s+)?cuts?\b", re.I),
    re.compile(r"\bcut\s+\$\s?\d", re.I),
    re.compile(r"\bprice\s+(?:cut|drop|reduction)s?\b", re.I),
    re.compile(r"\bcut\s+(?:\w+\s+)?(?:times|twice)\b", re.I),
    re.compile(r"\bsitting\s+\d+\s+days\b", re.I),
    re.compile(r"\b(?:on the market|on zillow|on redfin)\s+\d+\s+days\b", re.I),
    re.compile(r"\bmotivated\s+seller\b", re.I),
    re.compile(r"\brelisted\b|\bsecond run\b|\brough tenant\b", re.I),
]


def mentions_listing_pressure(text: Optional[str]) -> bool:
    """True when a draft points at a listing's price cuts / days on market."""
    if not text:
        return False
    return any(p.search(str(text)) for p in _LISTING_PRESSURE)
