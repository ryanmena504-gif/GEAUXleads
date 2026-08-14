"""Bloodhound's evidence-first recommendation and learning loop.

This intentionally does not pretend that a small Airtable table can predict a
conversion percentage.  It gives Ryan a clear work bucket today, then uses
only confirmed results to make future recommendations more specific.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.field_norm import clean_text, is_valid_email, is_valid_phone


CONTACT_NOW = "Contact Now"
WATCH = "Watch"
NOT_A_FIT = "Not a Fit"


def _text(record: Dict[str, Any], key: str) -> str:
    return (clean_text(record.get(key)) or "").strip()


def _has_public_contact(record: Dict[str, Any]) -> bool:
    return any((
        is_valid_phone(record.get("phone")),
        is_valid_phone(record.get("phone_alt")),
        is_valid_email(record.get("email")),
        is_valid_email(record.get("email_alt")),
    ))


def _is_not_a_fit(record: Dict[str, Any]) -> bool:
    values = " ".join(
        _text(record, key).lower()
        for key in ("status", "status_raw", "outcome", "hunt_status", "rejection_reason")
    )
    return any(term in values for term in (
        "do not contact", "not a fit", "disqualified", "rejected", "wrong project",
        "bad data", "utility", "demolition", "dumpster", "street cut",
    ))


def _is_estimate_requested(record: Dict[str, Any]) -> bool:
    values = " ".join(_text(record, key).lower() for key in (
        "status", "reply_classification", "reply_summary",
    ))
    return "estimate requested" in values or "quote requested" in values


def _confirmed_outcome(record: Dict[str, Any]) -> Optional[str]:
    """Return only outcomes Ryan or a source has actually confirmed."""
    status = _text(record, "status").lower()
    outcome = _text(record, "outcome").lower()
    reply = _text(record, "reply_classification").lower()
    outreach = _text(record, "outreach_status").lower()

    if record.get("flag_won") is True or status == "won" or record.get("closed_revenue"):
        return "won"
    if any(value in {"not interested", "lost", "do not contact"} for value in (status, outcome, reply)):
        return "not_interested"
    if _is_estimate_requested(record):
        return "estimate_requested"
    if "replied" in outreach or reply in {"reply received", "needs more information", "interested"}:
        return "replied"
    if "sent" in outreach:
        return "contacted"
    return None


@dataclass
class Recommendation:
    lead_id: Optional[str]
    work_bucket: str
    priority: str
    why_this_matters: str
    what_to_do_next: str
    learning_note: str
    evidence_gaps: List[str]
    confirmed_outcome: Optional[str]
    training_size: int
    confidence: str
    feature_importance: List[Dict[str, Any]]


class PredictiveEngine:
    """Compatibility name retained for existing API routes.

    The engine deliberately makes no dollar or conversion prediction.  It
    learns a small, auditable set of outcome patterns instead.
    """

    FEATURE_KEYS = ("source", "project_type", "city")
    MIN_PATTERN_SAMPLE = 3
    MIN_LEARNING_SAMPLE = 5

    def __init__(self):
        self._training_size = 0
        self._outcomes = Counter()
        self._feature_outcomes: Dict[str, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        self._model_version = 1

    def train(self, records: List[Dict[str, Any]]) -> None:
        self._training_size = 0
        self._outcomes = Counter()
        self._feature_outcomes = defaultdict(lambda: defaultdict(Counter))

        for record in records:
            outcome = _confirmed_outcome(record)
            if not outcome:
                continue
            self._training_size += 1
            self._outcomes[outcome] += 1
            for field in self.FEATURE_KEYS:
                value = _text(record, field)
                if value:
                    self._feature_outcomes[field][value][outcome] += 1

        self._model_version += 1

    def _matching_patterns(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns: List[Dict[str, Any]] = []
        for field in self.FEATURE_KEYS:
            value = _text(record, field)
            if not value:
                continue
            counts = self._feature_outcomes[field].get(value, Counter())
            sample = sum(counts.values())
            if sample < self.MIN_PATTERN_SAMPLE:
                continue
            strongest, count = counts.most_common(1)[0]
            if strongest in {"won", "estimate_requested", "replied"}:
                patterns.append({
                    "feature": field,
                    "value": value,
                    "outcome": strongest,
                    "sample": sample,
                    "count": count,
                })
        return sorted(patterns, key=lambda item: (item["count"], item["sample"]), reverse=True)

    def predict(self, record: Dict[str, Any]) -> Recommendation:
        gaps: List[str] = []
        outcome = _confirmed_outcome(record)
        has_contact = _has_public_contact(record)
        has_evidence = bool(_text(record, "source_url") or _text(record, "evidence_summary"))
        why = _text(record, "recommendation_reason")
        next_action = _text(record, "recommended_action") or _text(record, "next_best_action")

        if not has_evidence:
            gaps.append("A source link or evidence summary")
        if not has_contact and not _is_not_a_fit(record):
            gaps.append("A verified public business phone or email")
        if not why:
            gaps.append("A plain-English reason this fits your work")
        if not next_action and not _is_not_a_fit(record):
            gaps.append("A specific next step")

        if _is_not_a_fit(record):
            bucket = NOT_A_FIT
            priority = "Leave alone"
            why_text = why or "This record does not match the premium surface-work work Bloodhound is looking for."
            action_text = "Keep it out of your daily list. Do not contact it unless new evidence changes the fit."
        elif _is_estimate_requested(record):
            bucket = CONTACT_NOW
            priority = "High"
            why_text = why or "They have asked for pricing or an estimate, so this needs a timely human follow-up."
            action_text = "Prepare the estimate or arrange the information needed to price the work."
        elif has_contact and has_evidence:
            bucket = CONTACT_NOW
            priority = "High"
            why_text = why or "A qualified business has a public contact path and evidence of a relevant project or partnership fit."
            action_text = next_action or "Open a draft, contact the business yourself, then record what happened."
        else:
            bucket = WATCH
            priority = "Medium"
            why_text = why or "This may fit, but it is not ready for outreach yet."
            action_text = next_action or (
                "Find a verified public business contact before reaching out."
                if not has_contact else "Review the public evidence before reaching out."
            )

        patterns = self._matching_patterns(record)
        if self._training_size < self.MIN_LEARNING_SAMPLE:
            learning_note = (
                "Bloodhound is still learning from your real results. "
                "It will not claim a win rate until enough confirmed outcomes exist."
            )
            confidence = "learning"
        elif patterns:
            strongest = patterns[0]
            outcome_label = {
                "won": "won work",
                "estimate_requested": "estimate requests",
                "replied": "replies",
            }[strongest["outcome"]]
            learning_note = (
                f"Based on {strongest['sample']} confirmed results, {strongest['feature'].replace('_', ' ')} "
                f"“{strongest['value']}” has produced {outcome_label} {strongest['count']} time(s)."
            )
            confidence = "pattern found"
        else:
            learning_note = (
                "Bloodhound has confirmed results, but not enough matching history for this kind of opportunity yet."
            )
            confidence = "early"

        return Recommendation(
            lead_id=record.get("id"),
            work_bucket=bucket,
            priority=priority,
            why_this_matters=why_text,
            what_to_do_next=action_text,
            learning_note=learning_note,
            evidence_gaps=gaps,
            confirmed_outcome=outcome,
            training_size=self._training_size,
            confidence=confidence,
            feature_importance=patterns[:3],
        )

    def batch_predict(self, records: List[Dict[str, Any]]) -> List[Recommendation]:
        bucket_rank = {CONTACT_NOW: 0, WATCH: 1, NOT_A_FIT: 2}
        results = [self.predict(record) for record in records]
        results.sort(key=lambda result: (bucket_rank[result.work_bucket], result.priority != "High"))
        return results

    def model_status(self) -> Dict[str, Any]:
        return {
            "model_version": self._model_version,
            "training_size": self._training_size,
            "results_recorded": dict(self._outcomes),
            "learning_ready": self._training_size >= self.MIN_LEARNING_SAMPLE,
            "note": (
                "Bloodhound learns from confirmed results only. It does not use guessed outcomes or claim a conversion rate."
            ),
        }


_engine: Optional[PredictiveEngine] = None


def get_engine() -> PredictiveEngine:
    global _engine
    if _engine is None:
        _engine = PredictiveEngine()
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None


def train_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    engine = get_engine()
    engine.train(records)
    return engine.model_status()


def _as_dict(result: Recommendation) -> Dict[str, Any]:
    return {
        "lead_id": result.lead_id,
        "work_bucket": result.work_bucket,
        "priority": result.priority,
        "why_this_matters": result.why_this_matters,
        "what_to_do_next": result.what_to_do_next,
        "learning_note": result.learning_note,
        "evidence_gaps": result.evidence_gaps,
        "confirmed_outcome": result.confirmed_outcome,
        "training_size": result.training_size,
        "confidence": result.confidence,
        "feature_importance": result.feature_importance,
        # Retained as null so older callers cannot mistake a fabricated number
        # for a real probability or monetary forecast.
        "conversion_probability": None,
        "expected_value": None,
        "priority_score": None,
    }


def predict_for_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(get_engine().predict(record))


def batch_predict(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_as_dict(result) for result in get_engine().batch_predict(records)]
