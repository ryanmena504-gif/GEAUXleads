"""Human-reviewed reply helper for Bloodhound.

It never sends, archives, or changes a record.  It only helps Ryan identify the
next human step after he pastes a reply or records a result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.field_norm import clean_text


@dataclass
class ReplyClassification:
    intent: str
    urgency: str
    suggested_action: str
    key_phrases: List[str]


class ReplyIntelligence:
    PATTERNS = {
        "estimate_request": [r"\b(estimate|quote|bid|pricing|price|cost|ballpark)\b"],
        "site_visit": [r"\b(schedule|appointment|meet|site visit|come by|available)\b"],
        "referral": [r"\b(refer|referral|recommend|someone you know)\b"],
        "not_interested": [r"\b(not interested|no thanks|unsubscribe|stop|don't contact|already hired|found someone)\b"],
        "needs_info": [r"\b(more info|details|portfolio|references|insurance|warranty|license)\b"],
        "positive": [r"\b(yes|interested|sounds good|go ahead|ready|let's do)\b"],
    }

    ACTIONS = {
        "estimate_request": "Call or reply personally and get the details needed to prepare an estimate.",
        "site_visit": "Offer a couple of times for a site visit or call.",
        "referral": "Thank them and ask for an introduction to the right person.",
        "not_interested": "Respect the response. Mark Not interested and do not contact again.",
        "needs_info": "Send the specific proof or portfolio item they asked for, using a device-native draft.",
        "positive": "Reply personally while the conversation is warm and agree on the next step.",
        "unclear": "Read the reply yourself and decide the next step before changing the record.",
    }

    def classify(self, reply_text: Optional[str], lead_record: Optional[Dict[str, Any]] = None) -> ReplyClassification:
        text = clean_text(reply_text) or ""
        lowered = text.lower()
        matches: Dict[str, List[str]] = {}
        for intent, patterns in self.PATTERNS.items():
            phrases: List[str] = []
            for pattern in patterns:
                for match in re.finditer(pattern, lowered, re.IGNORECASE):
                    phrase = text[match.start():match.end()]
                    if phrase not in phrases:
                        phrases.append(phrase)
            if phrases:
                matches[intent] = phrases

        # A stop/unsubscribe instruction always wins over positive words.
        if "not_interested" in matches:
            intent = "not_interested"
        elif matches:
            intent = max(matches, key=lambda key: len(matches[key]))
        else:
            intent = "unclear"

        urgency = "high" if re.search(r"\b(today|asap|urgent|immediately|this week)\b", lowered) else "normal"
        return ReplyClassification(
            intent=intent,
            urgency=urgency,
            suggested_action=self.ACTIONS[intent],
            key_phrases=matches.get(intent, [])[:5],
        )

    def classify_lead_reply(self, lead_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Notes are not a reply field.  Do not mine them for pseudo-replies.
        reply_text = clean_text(lead_record.get("reply_summary")) or ""
        if not reply_text:
            return None
        result = self.classify(reply_text, lead_record)
        return {
            "lead_id": lead_record.get("id"),
            "reply_text_preview": reply_text[:200],
            "intent": result.intent,
            "urgency": result.urgency,
            "suggested_action": result.suggested_action,
            "key_phrases": result.key_phrases,
        }

    def batch_classify(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = [self.classify_lead_reply(record) for record in records]
        return [result for result in results if result is not None]


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
        "urgency": result.urgency,
        "suggested_action": result.suggested_action,
        "key_phrases": result.key_phrases,
    }


def classify_lead_replies(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return get_reply_intel().batch_classify(records)
