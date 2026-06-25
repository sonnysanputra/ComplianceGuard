"""
Fail-safe routing: the system must never auto-close a case it could not reliably
assess. Strictest rules win.
"""

from langgraph.graph import END
from app.orchestrator import (
    route_after_scoring, route_after_data_quality, INVESTIGATION, DATA_QUALITY_FLOOR,
)

GOOD_DQ = {"quality_score": 100, "severity": "GOOD"}
CLEAN_WF = {"is_match": False, "customer_screening": {"verdict": "NO_MATCH"},
            "recipient_screening": {"verdict": "NO_MATCH"}}


def _state(**kw):
    base = {"data_quality": GOOD_DQ, "watchlist_findings": CLEAN_WF,
            "risk_score": 10, "risk_factors": []}
    base.update(kw)
    return base


def test_low_data_quality_stops():
    assert route_after_scoring(_state(data_quality={"quality_score": DATA_QUALITY_FLOOR - 1})) is END


def test_tool_failure_goes_to_human():
    assert route_after_scoring(_state(errors=[{"agent": "watchlist_screening"}])) == "human_approval"
    assert route_after_scoring(_state(errors=[{"agent": "policy_rag"}])) == "human_approval"


def test_high_risk_drafts_sar():
    assert route_after_scoring(_state(risk_score=85, risk_factors=[{"x": 1}])) == "sar_drafting"


def test_watchlist_match_needs_human_even_sub_threshold():
    wf = {"is_match": True, "customer_screening": {"verdict": "NO_MATCH"},
          "recipient_screening": {"verdict": "NO_MATCH"}}
    assert route_after_scoring(_state(watchlist_findings=wf, risk_score=20)) == "human_approval"
    # a possible (fuzzy) match also goes to a human
    wf2 = {"is_match": False, "customer_screening": {"verdict": "NO_MATCH"},
           "recipient_screening": {"verdict": "POSSIBLE_MATCH_REQUIRES_REVIEW"}}
    assert route_after_scoring(_state(watchlist_findings=wf2)) == "human_approval"


def test_partial_data_needs_human():
    dq = {"quality_score": 75, "severity": "PARTIAL"}
    assert route_after_scoring(_state(data_quality=dq, risk_factors=[{"x": 1}])) == "human_approval"


def test_sub_threshold_triggered_goes_to_fp_review():
    assert route_after_scoring(_state(risk_factors=[{"x": 1}], risk_score=30)) == "false_positive_review"


def test_clean_low_risk_auto_closes():
    assert route_after_scoring(_state()) is END


def test_errors_beat_high_risk():
    # a failed tool must not auto-draft a SAR even on a high score
    assert route_after_scoring(_state(risk_score=90, errors=[{"agent": "watchlist_screening"}])) == "human_approval"


def test_data_quality_gate():
    assert route_after_data_quality({"data_quality": {"can_continue": True}}) == INVESTIGATION
    assert route_after_data_quality({"data_quality": {"can_continue": False}}) is END
