"""
Risk-aware priority + SLA: priority reflects the full investigation, and each
priority carries a review deadline.
"""

from app.core.priority import assess_priority, sla_due_at, sla_label, PRIORITY_SLA


def test_p1_on_confirmed_sanctions_match():
    state = {"risk_score": 50, "watchlist_findings": {
        "is_match": True, "list_type": "UN_SANCTIONS", "best_match": "Acme"}}
    p, reason = assess_priority(state)
    assert p == "P1" and "UN_SANCTIONS" in reason


def test_p1_on_critical_score_and_many_factors():
    assert assess_priority({"risk_score": 90})[0] == "P1"
    factors = [{"name": "A", "severity": "HIGH"}, {"name": "B", "severity": "CRITICAL"},
               {"name": "C", "severity": "HIGH"}]
    assert assess_priority({"risk_score": 40, "risk_factors": factors})[0] == "P1"


def test_p2_on_high_score_mule_or_country_plus_new_recipient():
    assert assess_priority({"risk_score": 70})[0] == "P2"
    assert assess_priority({"risk_score": 10,
                            "transaction_findings": {"typology": "money mule"}})[0] == "P2"
    assert assess_priority({"risk_score": 10,
        "watchlist_findings": {"high_risk_country": True},
        "transaction_findings": {"flags": {"new_overseas_recipient": True}}})[0] == "P2"


def test_p3_on_medium_or_unclear_no_watchlist():
    assert assess_priority({"risk_score": 45})[0] == "P3"
    assert assess_priority({"risk_score": 25, "watchlist_findings": {"is_match": False}})[0] == "P3"


def test_p4_on_cleared_false_positive():
    state = {"risk_score": 15,
             "fp_review": {"requires_human_review": False, "clearance_reason": "documented supplier"}}
    p, reason = assess_priority(state)
    assert p == "P4" and "false-positive" in reason


def test_sla_due_and_labels():
    assert sla_due_at("P1") is not None          # immediate -> concrete deadline
    assert sla_due_at("P2") is not None
    assert sla_due_at("P4") is None              # batch, no hard deadline
    for p in ("P1", "P2", "P3", "P4"):
        assert sla_label(p) == PRIORITY_SLA[p]["label"]


def test_sla_anchored_to_start_time():
    due = sla_due_at("P2", "2026-06-24T10:00:00+00:00")   # +4h
    assert due.startswith("2026-06-24T14:00")
