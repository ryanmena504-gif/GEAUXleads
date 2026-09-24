"""Unit tests for the Band A Slack dedupe/threshold logic.

Runs offline — no real Slack calls, no real Mongo required (SlackAlerter is
instantiated without connecting because ._reason is pure).
"""
import pytest

from services.slack_service import SlackAlerter, ALERT_SCORE_DELTA, _build_blocks


class _Stub(SlackAlerter):
    def __init__(self):  # skip parent Mongo connect
        pass


@pytest.fixture
def alerter():
    return _Stub()


def _opp(band, score):
    return {"id": "recX", "priority_band": band, "priority_score": score}


def test_band_a_new_lead_fires(alerter):
    assert alerter._reason(_opp("A", 72), prior=None) == "new"


def test_band_b_never_fires(alerter):
    assert alerter._reason(_opp("B", 68), prior=None) is None
    assert alerter._reason(_opp("B", 99), prior=None) is None


def test_band_a_below_delta_does_not_refire(alerter):
    prior = {"last_alerted_score": 72}
    # +9 is below the 10-point threshold
    assert alerter._reason(_opp("A", 81), prior=prior) is None


def test_band_a_at_delta_refires(alerter):
    prior = {"last_alerted_score": 72}
    assert alerter._reason(_opp("A", 72 + ALERT_SCORE_DELTA), prior=prior) == "promoted"


def test_band_a_missing_scores_do_not_refire(alerter):
    prior = {"last_alerted_score": None}
    assert alerter._reason(_opp("A", 80), prior=prior) is None
    prior = {"last_alerted_score": 70}
    assert alerter._reason({"id": "recX", "priority_band": "A", "priority_score": None},
                           prior=prior) is None


def test_blocks_include_dashboard_link_and_next_action():
    opp = {
        "id": "rec9oACK2PGWSmfmk",
        "name": "Greige Interiors",
        "priority_band": "A",
        "priority_score": 83,
        "confidence_score": 72,
        "lane_label": "Partner Pipeline",
        "source": "Website",
        "project_address": "New Orleans, LA",
        "recommendation_reason": "Strong signal from Parade of Homes work",
        "next_best_action": "Reach out with sample-board collab",
    }
    blocks = _build_blocks(opp, reason="new")
    joined = str(blocks)
    assert "Greige Interiors" in joined
    assert "Partner Pipeline" in joined
    assert "Reach out" in joined
    assert "/opportunities/rec9oACK2PGWSmfmk" in joined
    assert "Notification only" in joined
