"""
Analyst feedback learning: when a human previously overrode the AI as a false
positive, the Case Memory Agent lowers confidence on similar future cases.
"""

import app.agents.case_memory as cm
from app.agents.case_memory import case_memory


def _run(monkeypatch, prior_cases, decisions, cust=None):
    monkeypatch.setattr(cm, "get_customer", lambda cid: cust or
                        {"customer_id": cid, "previous_alerts": 0})
    monkeypatch.setattr(cm, "get_customer_history",
                        lambda cid, exclude_case_id="": {"cases": prior_cases, "decisions": decisions})
    state = {"alert": {"id": "AML-NOW", "customer_id": "CUST-1",
                       "recipient": "Supplier ABC Sdn Bhd"}}
    return case_memory.run(state)["memory_findings"]


def test_analyst_false_positive_override_reduces(monkeypatch):
    prior = [{"case_id": "OLD-1", "risk_level": "MEDIUM", "recipient": "Supplier ABC Sdn Bhd"}]
    decisions = [{"decision": "reject", "analyst_agrees_with_ai": False,
                  "feedback_tags": ["false_positive"]}]
    mf = _run(monkeypatch, prior, decisions)
    assert mf["analyst_false_positive_feedback"] == 1
    # even though the same recipient was seen before, analyst FP feedback -> reduce
    assert mf["memory_risk_direction"] == "reduce"
    assert "false positive" in mf["memory_risk_signal"].lower()
    assert "reduce confidence" in mf["memory_risk_signal"].lower()


def test_corrected_typology_is_surfaced(monkeypatch):
    decisions = [{"decision": "reject", "analyst_agrees_with_ai": False,
                  "feedback_tags": ["wrong_typology"], "corrected_typology": "legitimate supplier payment"}]
    mf = _run(monkeypatch, [], decisions)
    assert "legitimate supplier payment" in mf["analyst_corrections"]
    assert "wrong_typology" in mf["analyst_feedback_tags"]
    assert "legitimate supplier payment" in mf["memory_risk_signal"]


def test_confirmed_escalation_still_dominates(monkeypatch):
    # a prior HIGH escalation outweighs an FP override -> still increase
    prior = [{"case_id": "OLD-1", "risk_level": "HIGH", "recipient": "X"}]
    decisions = [{"decision": "reject", "analyst_agrees_with_ai": False,
                  "feedback_tags": ["false_positive"]}]
    mf = _run(monkeypatch, prior, decisions)
    assert mf["memory_risk_direction"] == "increase"


def test_no_feedback_is_neutral(monkeypatch):
    mf = _run(monkeypatch, [], [])
    assert mf["analyst_false_positive_feedback"] == 0
    assert mf["memory_risk_direction"] == "neutral"
