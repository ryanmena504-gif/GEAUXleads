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
