from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.field_norm import clean_text

log = logging.getLogger("bloodhound.reply_intel")


@dataclass
class ReplyClassification:
    intent: str
    sentiment: str
    urgency: str
    confidence: float
    suggested_action: str
    suggested_response_template: Optional[str]
    key_phrases: List[str]


class ReplyIntelligence:
    INTENT_PATTERNS = {
        "estimate_request": [
            r"\b(estimate|quote|bid|pricing|price|cost|how much)\b",
            r"\b(ballpark|range|figure|numbers?)\b",
            r"\b(send|give).{0,20}(estimate|quote|price)\b",
        ],
        "scheduling": [
            r"\b(schedule|appointment|meet|meeting|visit|site visit|come by|stop by|when|available|time|day|week)\b",
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|morning|afternoon)\b",
            r"\b(next week|this week|tomorrow|soon)\b",
        ],
        "referral": [
            r"\b(refer|referral|recommend|someone|friend|neighbor|colleague|contact|know a)\b",
            r"\b(not me|wrong person|different|someone else)\b",
        ],
        "not_interested": [
            r"\b(not interested|no thanks|pass|decline|unsubscribe|stop|don'?t contact|wrong number|sold|already hired|found someone)\b",
            r"\b(no need|don'?t need|not looking|not right now|maybe later)\b",
        ],
        "objection": [
            r"\b(too expensive|too much|high price|cheaper|discount|budget|can'?t afford)\b",
            r"\b(compare|comparison|shopping around|other quotes|getting bids)\b",
            r"\b(not sure|hesitant|concern|worried|skeptical|trust|license|insured|bonded)\b",
            r"\b(timeline|too long|how long|when finished|deadline|rush)\b",
        ],
        "positive": [
            r"\b(yes|interested|sounds good|let'?s do|go ahead|proceed|ready|excited|perfect|great|awesome)\b",
            r"\b(love|like|want|need|help|please)\b",
        ],
        "needs_info": [
            r"\b(more info|details|question|what|how|why|explain|tell me|portfolio|past work|references|reviews)\b",
            r"\b(experience|qualified|certified|license number|insurance|warranty|guarantee)\b",
        ],
    }

    SENTIMENT_POSITIVE = [
        r"\b(thank|thanks|appreciate|great|awesome|perfect|excellent|love|like|interested|excited|ready)\b",
        r"\b(yes|sure|absolutely|definitely|of course|please|help)\b",
    ]
    SENTIMENT_NEGATIVE = [
        r"\b(no|not|never|stop|don'?t|won'?t|can'?t|bad|terrible|awful|waste|scam|annoying)\b",
        r"\b(expensive|too much|rip off|overpriced|disappointed|frustrated|angry)\b",
    ]

    URGENCY_HIGH = [
        r"\b(urgent|asap|immediately|emergency|rush|today|now|right away|hurry)\b",
    ]
    URGENCY_MEDIUM = [
        r"\b(soon|this week|next week|quick|fast|promptly)\b",
    ]

    ACTION_TEMPLATES = {
        "estimate_request": {
            "action": "Prepare Estimate",
            "template": "Thanks for your interest! I'd be happy to prepare a detailed estimate for {project_type} at {address}. When would be a good time to visit the site?",
        },
        "scheduling": {
            "action": "Schedule Site Visit",
            "template": "I'd love to come by and take a look. What days/times work best for you this week or next?",
        },
        "referral": {
            "action": "Follow Up on Referral",
            "template": "Thank you for the referral! Would you mind sharing their contact info, or would you prefer to introduce us directly?",
        },
        "not_interested": {
            "action": "Archive & Tag",
            "template": None,
        },
        "objection": {
            "action": "Address Concerns",
            "template": "I completely understand. Let me address that. Would a quick call help clarify?",
        },
        "positive": {
            "action": "Move to Contract",
            "template": "Excellent! Let's get started. I'll send over the next steps and we can schedule the kickoff.",
        },
        "needs_info": {
            "action": "Send Details",
            "template": "Happy to provide more details. Here's what you need to know about our {project_type} process...",
        },
        "unclear": {
            "action": "Clarify Intent",
            "template": "Thanks for reaching out! Just to make sure I understand — are you looking for an estimate, or do you have questions about the process?",
        },
    }

    def classify(self, reply_text: Optional[str], lead_record: Optional[Dict[str, Any]] = None) -> ReplyClassification:
        text = clean_text(reply_text) or ""
        lowered = text.lower()

        if not text:
            return ReplyClassification(
                intent="unclear", sentiment="neutral", urgency="low",
                confidence=0.0, suggested_action="Review manually",
                suggested_response_template=None, key_phrases=[],
            )

        intent_scores: Dict[str, float] = {}
        matched_phrases: List[str] = []

        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                matches = list(re.finditer(pattern, lowered, re.IGNORECASE))
                if matches:
                    score += len(matches) * 0.3
                    for m in matches:
                        phrase = text[m.start():m.end()]
                        if phrase not in matched_phrases:
                            matched_phrases.append(phrase)
            if score > 0:
                intent_scores[intent] = min(score, 1.0)

        if "estimate_request" in intent_scores and self._has_positive(lowered):
            intent_scores["estimate_request"] += 0.2

        if "not_interested" in intent_scores:
            intent_scores["not_interested"] += 0.15

        if intent_scores:
            top_intent = max(intent_scores, key=intent_scores.get)
            confidence = min(intent_scores[top_intent], 0.95)
        else:
            top_intent = "unclear"
            confidence = 0.3

        pos_count = sum(1 for p in self.SENTIMENT_POSITIVE if re.search(p, lowered, re.IGNORECASE))
        neg_count = sum(1 for p in self.SENTIMENT_NEGATIVE if re.search(p, lowered, re.IGNORECASE))

        if pos_count > neg_count:
            sentiment = "positive"
        elif neg_count > pos_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        if top_intent == "not_interested":
            sentiment = "negative"

        if any(re.search(p, lowered, re.IGNORECASE) for p in self.URGENCY_HIGH):
            urgency = "high"
        elif any(re.search(p, lowered, re.IGNORECASE) for p in self.URGENCY_MEDIUM):
            urgency = "medium"
        else:
            urgency = "low"

        action_info = self.ACTION_TEMPLATES.get(top_intent, self.ACTION_TEMPLATES["unclear"])
        template = action_info["template"]

        if template and lead_record:
            template = template.replace("{project_type}", clean_text(lead_record.get("project_type")) or "this project")
            template = template.replace("{address}", clean_text(lead_record.get("project_address") or lead_record.get("address")) or "your property")
            template = template.replace("{name}", clean_text(lead_record.get("decision_maker") or lead_record.get("contact_name") or "there"))

        return ReplyClassification(
            intent=top_intent, sentiment=sentiment, urgency=urgency,
            confidence=round(confidence, 2),
            suggested_action=action_info["action"],
            suggested_response_template=template,
            key_phrases=matched_phrases[:5],
        )

    def _has_positive(self, text: str) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in self.SENTIMENT_POSITIVE)

    def classify_lead_reply(self, lead_record: Dict[str, Any]) -> Dict[str, Any]:
        reply_text = clean_text(lead_record.get("reply_summary")) or ""
        if not reply_text:
            reply_text = clean_text(lead_record.get("notes")) or ""
        result = self.classify(reply_text, lead_record)
        return {
            "lead_id": lead_record.get("id"),
            "reply_text_preview": reply_text[:200] if reply_text else None,
            "intent": result.intent,
            "sentiment": result.sentiment,
            "urgency": result.urgency,
            "confidence": result.confidence,
            "suggested_action": result.suggested_action,
            "suggested_response": result.suggested_response_template,
            "key_phrases": result.key_phrases,
        }

    def batch_classify(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for r in records:
            if clean_text(r.get("reply_summary")) or clean_text(r.get("notes")):
                results.append(self.classify_lead_reply(r))
        results.sort(key=lambda x: (
            {"high": 3, "medium": 2, "low": 1}.get(x["urgency"], 0),
            x["confidence"],
        ), reverse=True)
        return results


_reply_intel: Optional[ReplyIntelligence] = None


def get_reply_intel() -> ReplyIntelligence:
    global _reply_intel
    if _reply_intel is None:
        _reply_intel = ReplyIntelligence()
    return _reply_intel


def classify_reply(reply_text: str, lead_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = get_reply_intel().classify(reply_text, lead_record)
    return {
        "intent": result.intent,
        "sentiment": result.sentiment,
        "urgency": result.urgency,
        "confidence": result.confidence,
        "suggested_action": result.suggested_action,
        "suggested_response": result.suggested_response_template,
        "key_phrases": result.key_phrases,
    }


def classify_lead_replies(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return get_reply_intel().batch_classify(records)
