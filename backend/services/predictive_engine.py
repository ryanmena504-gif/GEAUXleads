from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.field_norm import coerce_number, clean_text, is_valid_email, is_valid_phone

log = logging.getLogger("bloodhound.predictive")


@dataclass
class FeatureWeight:
    name: str
    won_count: int = 0
    lost_count: int = 0
    total_count: int = 0

    @property
    def conversion_rate(self) -> float:
        if self.total_count == 0:
            return 0.5
        return (self.won_count + 1) / (self.total_count + 2)

    @property
    def lift(self) -> float:
        return self.conversion_rate / 0.5


@dataclass
class PredictionResult:
    lead_id: Optional[str]
    conversion_probability: float
    expected_value: Optional[float]
    priority_score: float
    feature_importance: List[Dict[str, Any]]
    confidence: str
    model_version: int


class PredictiveEngine:
    FEATURE_EXTRACTORS = {
        "has_phone": lambda r: bool(
            is_valid_phone(r.get("phone")) or is_valid_phone(r.get("phone_alt"))
            or is_valid_phone(r.get("contact_phone")) or is_valid_phone(r.get("phone_number"))
        ),
        "has_email": lambda r: bool(
            is_valid_email(r.get("email")) or is_valid_email(r.get("email_alt"))
            or is_valid_email(r.get("contact_email"))
        ),
        "has_decision_maker": lambda r: bool(
            clean_text(r.get("decision_maker")) or clean_text(r.get("contact_name"))
        ),
        "has_company": lambda r: bool(
            clean_text(r.get("company")) or clean_text(r.get("contact_company"))
            or clean_text(r.get("business_name"))
        ),
        "has_address": lambda r: bool(
            clean_text(r.get("project_address")) or clean_text(r.get("address"))
        ),
        "has_permit": lambda r: bool(clean_text(r.get("permit_number"))),
        "ai_complete": lambda r: (clean_text(r.get("ai_status")) or "").lower() == "complete",
        "has_evidence": lambda r: bool(clean_text(r.get("evidence_summary"))),
        "has_recommendation": lambda r: bool(
            clean_text(r.get("recommendation_reason")) or clean_text(r.get("why_lead_matters"))
        ),
        "has_estimated_value": lambda r: coerce_number(
            r.get("estimated_value") or r.get("estimated_job_value")
        ) is not None,
        "has_construction_value": lambda r: coerce_number(
            r.get("construction_value") or r.get("permit_project_value")
        ) is not None,
        "verified": lambda r: bool(r.get("flag_verified") or r.get("verified_opportunity")),
        "qualified": lambda r: bool(r.get("flag_qualified") or r.get("qualified_opportunity")),
        "premium": lambda r: bool(r.get("flag_premium")),
        "partnership": lambda r: bool(r.get("flag_partnership")),
        "recent_activity": lambda r: bool(r.get("flag_recent_activity")),
        "local_service": lambda r: bool(r.get("flag_local_service")),
        "bathroom_signal": lambda r: bool(r.get("flag_bathroom_signal")),
        "has_outreach_angle": lambda r: bool(clean_text(r.get("outreach_angle"))),
        "has_first_message": lambda r: bool(clean_text(r.get("first_message"))),
        "high_confidence": lambda r: (clean_text(
            r.get("contact_confidence") or r.get("contact_confidence_raw")
        ) or "").lower() in ("high", "strong", "verified", "confirmed"),
    }

    def __init__(self):
        self._weights: Dict[str, FeatureWeight] = {
            name: FeatureWeight(name=name) for name in self.FEATURE_EXTRACTORS
        }
        self._baseline_rate = 0.15
        self._training_size = 0
        self._model_version = 1

    def train(self, records: List[Dict[str, Any]]) -> None:
        won_total = 0
        lost_total = 0
        for record in records:
            outcome = self._extract_outcome(record)
            if outcome is None:
                continue
            is_won = outcome == "won"
            if is_won:
                won_total += 1
            else:
                lost_total += 1
            for feat_name, extractor in self.FEATURE_EXTRACTORS.items():
                present = extractor(record)
                weight = self._weights[feat_name]
                weight.total_count += 1
                if is_won and present:
                    weight.won_count += 1
                elif not is_won and present:
                    weight.lost_count += 1
        total_outcomes = won_total + lost_total
        if total_outcomes > 0:
            self._baseline_rate = (won_total + 1) / (total_outcomes + 2)
            self._training_size = total_outcomes
            self._model_version += 1
            log.info(
                "PredictiveEngine: trained on %d outcomes (%d won, %d lost). Baseline %.2f%%",
                total_outcomes, won_total, lost_total, self._baseline_rate * 100
            )

    def _extract_outcome(self, record: Dict[str, Any]) -> Optional[str]:
        if record.get("flag_won") is True or record.get("job_won") is True:
            return "won"
        if record.get("outcome") and "not interested" in str(record.get("outcome")).lower():
            return "lost"
        if record.get("status") == "Lost" or record.get("status_raw") == "Lost":
            return "lost"
        if record.get("reply_classification") and "not interested" in str(record.get("reply_classification")).lower():
            return "lost"
        rev = coerce_number(record.get("closed_revenue"))
        if rev and rev > 0:
            return "won"
        return None

    def predict(self, record: Dict[str, Any]) -> PredictionResult:
        log_odds = math.log(self._baseline_rate / (1 - self._baseline_rate))
        feature_scores = []

        for feat_name, extractor in self.FEATURE_EXTRACTORS.items():
            present = extractor(record)
            weight = self._weights[feat_name]
            if present:
                feat_rate = weight.conversion_rate
                feat_lift = feat_rate / max(self._baseline_rate, 0.01)
                contribution = math.log(feat_rate / (1 - feat_rate + 0.001)) if feat_rate < 0.99 else 2.0
                log_odds += contribution * 0.3
                feature_scores.append({
                    "feature": feat_name,
                    "present": True,
                    "conversion_rate": round(feat_rate, 3),
                    "lift": round(feat_lift, 2),
                    "weight": round(contribution * 0.3, 3),
                })
            elif weight.total_count > 0:
                feat_rate = weight.conversion_rate
                if feat_rate > self._baseline_rate:
                    contribution = -0.1 * (feat_rate - self._baseline_rate)
                    log_odds += contribution

        probability = 1 / (1 + math.exp(-log_odds))
        probability = max(0.01, min(0.99, probability))
        priority_score = probability * 100

        est_value = coerce_number(record.get("estimated_value") or record.get("estimated_job_value"))
        expected_value = est_value * probability if est_value else None

        if self._training_size >= 50:
            confidence = "high"
        elif self._training_size >= 10:
            confidence = "medium"
        else:
            confidence = "low"

        feature_scores.sort(key=lambda x: abs(x.get("weight", 0)), reverse=True)

        return PredictionResult(
            lead_id=record.get("id"),
            conversion_probability=round(probability, 3),
            expected_value=round(expected_value, 2) if expected_value else None,
            priority_score=round(priority_score, 1),
            feature_importance=feature_scores[:8],
            confidence=confidence,
            model_version=self._model_version,
        )

    def batch_predict(self, records: List[Dict[str, Any]]) -> List[PredictionResult]:
        results = [self.predict(r) for r in records]
        results.sort(key=lambda p: (p.expected_value or 0, p.conversion_probability), reverse=True)
        return results

    def model_status(self) -> Dict[str, Any]:
        return {
            "model_version": self._model_version,
            "training_size": self._training_size,
            "baseline_rate": round(self._baseline_rate, 3),
            "features_tracked": len(self._weights),
            "top_features": sorted(
                [
                    {"name": w.name, "conversion_rate": round(w.conversion_rate, 3), "n": w.total_count}
                    for w in self._weights.values() if w.total_count > 0
                ],
                key=lambda x: x["conversion_rate"],
                reverse=True,
            )[:10],
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


def predict_for_record(record: Dict[str, Any]) -> Dict[str, Any]:
    engine = get_engine()
    result = engine.predict(record)
    return {
        "lead_id": result.lead_id,
        "conversion_probability": result.conversion_probability,
        "expected_value": result.expected_value,
        "priority_score": result.priority_score,
        "feature_importance": result.feature_importance,
        "confidence": result.confidence,
        "model_version": result.model_version,
    }


def batch_predict(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    engine = get_engine()
    results = engine.batch_predict(records)
    return [
        {
            "lead_id": r.lead_id,
            "conversion_probability": r.conversion_probability,
            "expected_value": r.expected_value,
            "priority_score": r.priority_score,
            "feature_importance": r.feature_importance,
            "confidence": r.confidence,
        }
        for r in results
    ]
