"""
learning_service.py — the read-only outcome-learning loop.

Rules honored:
- No governed-field mutation. This service NEVER writes to opportunities,
  Airtable, or any external store. It aggregates over data Ryan already
  confirmed with an explicit "I sent it" / "Replied" / "Not interested"
  outcome.
- No LLM call, no external network. Pure Python aggregation.
- Sample-size safe. An insight only surfaces when it has at least 3
  observations on both sides of the comparison, so a single lucky reply
  can't turn into a false pattern.

Data source: the opportunity list itself. Each record already carries
`outreach_status`, `date_replied`, `status`, and the 17 governed fields.
Nothing new is stored — this is a read-through.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ---- outcome buckets ---------------------------------------------------------

# Positive reply outcomes — the classifier's approval got a response.
POSITIVE_REPLIES = {"Replied", "Estimate requested"}
# Negative reply outcomes — outreach happened, no traction.
NEGATIVE_REPLIES = {"No response", "Not interested"}
# Any outreach event tells us the classifier promoted this record.
ANY_OUTREACH = POSITIVE_REPLIES | NEGATIVE_REPLIES | {"Sent"}

# Statuses that count as a closed sale / closed loss for win-rate insights.
WON_STATUSES = {"Won"}
LOST_STATUSES = {"Lost", "Disqualified"}

# The governed dimensions we compare. Each is (dto_key, human_label).
DIMENSIONS: List[Tuple[str, str]] = [
    ("money_signal", "Money Signal"),
    ("premium_fit", "Premium Fit"),
    ("freshness", "Freshness"),
    ("evidence_status", "Evidence"),
    ("source", "Source"),
]

# An insight only surfaces if BOTH sides of the comparison have ≥ this many
# observations. Prevents "5/5 replied when premium=Strong" from firing when
# only 5 leads have ever been sent.
MIN_OBS_PER_VALUE = 3
# Overall pool minimum before any insight can render at all.
MIN_TOTAL_OBSERVATIONS = 6


# ---- data shapes -------------------------------------------------------------


@dataclass
class Insight:
    """One learned pattern shown on the Home dashboard."""
    kind: str            # "reply_rate" | "win_rate"
    dimension: str       # "Premium Fit" — human label
    value: str           # "Strong"
    positives: int
    total: int
    baseline_rate: float  # 0..1 — rate across ALL observations
    focus_rate: float     # 0..1 — rate when dimension == value
    lift: float          # focus_rate / max(baseline_rate, 0.05)
    headline: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "dimension": self.dimension,
            "value": self.value,
            "positives": self.positives,
            "total": self.total,
            "baseline_rate": round(self.baseline_rate, 3),
            "focus_rate": round(self.focus_rate, 3),
            "lift": round(self.lift, 2),
            "headline": self.headline,
            "detail": self.detail,
        }


# ---- helpers -----------------------------------------------------------------


def _observations_for_replies(opps: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], bool]]:
    """Return (opp, positive_bool) for every record that has an outreach outcome."""
    out: List[Tuple[Dict[str, Any], bool]] = []
    for o in opps:
        status = (o.get("outreach_status") or "").strip()
        if status in POSITIVE_REPLIES:
            out.append((o, True))
        elif status in NEGATIVE_REPLIES:
            out.append((o, False))
    return out


def _observations_for_wins(opps: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], bool]]:
    """Return (opp, won_bool) for every closed record."""
    out: List[Tuple[Dict[str, Any], bool]] = []
    for o in opps:
        status = (o.get("status") or "").strip()
        if status in WON_STATUSES:
            out.append((o, True))
        elif status in LOST_STATUSES:
            out.append((o, False))
    return out


def _dimension_value(opp: Dict[str, Any], key: str) -> Optional[str]:
    raw = opp.get(key)
    if raw is None:
        return None
    val = str(raw).strip()
    return val or None


def _rank_score(insight: Insight) -> float:
    """Rank by absolute delta from baseline, weighted by sqrt(sample size).

    This surfaces patterns that are BOTH meaningfully different from the
    baseline AND grounded in enough observations to feel real.
    """
    from math import sqrt
    return abs(insight.focus_rate - insight.baseline_rate) * sqrt(insight.total)


def _build_insights_for(
    kind: str,
    observations: List[Tuple[Dict[str, Any], bool]],
) -> List[Insight]:
    if len(observations) < MIN_TOTAL_OBSERVATIONS:
        return []

    total_pos = sum(1 for _, p in observations if p)
    baseline_rate = total_pos / len(observations) if observations else 0.0

    insights: List[Insight] = []
    for key, label in DIMENSIONS:
        # Bucket observations by dimension value.
        by_value: Dict[str, List[bool]] = defaultdict(list)
        for opp, positive in observations:
            v = _dimension_value(opp, key)
            if v is None:
                continue
            by_value[v].append(positive)

        for value, outcomes in by_value.items():
            if len(outcomes) < MIN_OBS_PER_VALUE:
                continue
            pos = sum(1 for x in outcomes if x)
            focus_rate = pos / len(outcomes)
            # Require an actual delta from baseline (either direction).
            if abs(focus_rate - baseline_rate) < 0.15:
                continue
            lift = focus_rate / max(baseline_rate, 0.05)
            insights.append(_shape_insight(
                kind=kind,
                dimension=label,
                value=value,
                positives=pos,
                total=len(outcomes),
                baseline_rate=baseline_rate,
                focus_rate=focus_rate,
                lift=lift,
            ))

    insights.sort(key=_rank_score, reverse=True)
    return insights


def _shape_insight(**kw) -> Insight:
    kind = kw["kind"]
    label = kw["dimension"]
    value = kw["value"]
    positives = kw["positives"]
    total = kw["total"]
    focus_rate = kw["focus_rate"]
    baseline_rate = kw["baseline_rate"]
    lift = kw["lift"]

    # Base-form verb for "more likely to ___" phrases; past-tense for the
    # "N of M ___" detail line.
    verb_base = "reply" if kind == "reply_rate" else "close as Won"
    verb_past = "replied" if kind == "reply_rate" else "closed as Won"
    negative_phrase = "went cold" if kind == "reply_rate" else "closed Lost"
    direction = "more likely" if focus_rate > baseline_rate else "less likely"

    if lift >= 1.15 and focus_rate > baseline_rate:
        lift_phrase = f"{lift:.1f}× more likely to {verb_base}"
    elif focus_rate < baseline_rate:
        lift_phrase = f"more often {negative_phrase}"
    else:
        lift_phrase = f"{direction} to {verb_base}"

    headline = f"{label} = {value} · {lift_phrase}"
    detail = (
        f"{positives} of {total} {verb_past} "
        f"(vs {baseline_rate * 100:.0f}% baseline)."
    )
    return Insight(
        kind=kind,
        dimension=label,
        value=value,
        positives=positives,
        total=total,
        baseline_rate=baseline_rate,
        focus_rate=focus_rate,
        lift=lift,
        headline=headline,
        detail=detail,
    )


# ---- public entrypoint -------------------------------------------------------


def compute_insights(opps: List[Dict[str, Any]], limit: int = 3) -> Dict[str, Any]:
    """Compute up to `limit` learning-loop insights from the opportunity list.

    Returns a stable envelope with counts so the UI can show:
      • the top learned patterns, or
      • an honest "learning starts after N more outcomes" message.
    """
    reply_obs = _observations_for_replies(opps)
    win_obs = _observations_for_wins(opps)

    reply_insights = _build_insights_for("reply_rate", reply_obs)
    win_insights = _build_insights_for("win_rate", win_obs)

    combined: List[Insight] = []
    combined.extend(reply_insights)
    combined.extend(win_insights)
    combined.sort(key=_rank_score, reverse=True)

    top = combined[: max(0, limit)]

    return {
        "observations": {
            "replies": len(reply_obs),
            "wins": len(win_obs),
            "min_required": MIN_TOTAL_OBSERVATIONS,
        },
        "baseline": {
            "reply_rate": round(
                (sum(1 for _, p in reply_obs if p) / len(reply_obs)) if reply_obs else 0.0,
                3,
            ),
            "win_rate": round(
                (sum(1 for _, p in win_obs if p) / len(win_obs)) if win_obs else 0.0,
                3,
            ),
        },
        "insights": [i.to_dict() for i in top],
    }
