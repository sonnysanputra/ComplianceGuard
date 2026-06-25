"""
Data quality grades the case (GOOD / PARTIAL / POOR / CRITICAL_MISSING) rather
than a binary complete/incomplete, and decides whether it can continue.
"""

import app.agents.data_quality as dqmod
from app.agents.data_quality import data_quality

FULL_CUST = {"customer_id": "C1", "occupation": "Engineer", "declared_income": 8000,
             "kyc_status": "Completed"}
TXNS = [{"amount": 100, "recipient": "X"}]


def _run(monkeypatch, cust, txns, alert=None):
    monkeypatch.setattr(dqmod, "get_customer", lambda cid: cust)
    monkeypatch.setattr(dqmod, "get_transactions", lambda cid: txns)
    state = {"alert": {"customer_id": "C1", "recipient": "Acme",
                       "supporting_document": "INV-1", **(alert or {})}}
    return data_quality.run(state)["data_quality"]


def test_good_when_all_present(monkeypatch):
    dq = _run(monkeypatch, FULL_CUST, TXNS)
    assert dq["severity"] == "GOOD"
    assert dq["quality_score"] == 100
    assert dq["complete"] and dq["can_continue"]


def test_critical_missing_when_no_profile_or_txns(monkeypatch):
    dq = _run(monkeypatch, None, [])
    assert dq["severity"] == "CRITICAL_MISSING"
    assert "customer_profile" in dq["missing_critical_fields"]
    assert dq["can_continue"] is False
    assert "Halt" in dq["recommended_action"]


def test_poor_when_recipient_missing(monkeypatch):
    dq = _run(monkeypatch, FULL_CUST, TXNS, alert={"recipient": ""})
    assert dq["severity"] == "POOR"
    assert "recipient_details" in dq["missing_critical_fields"]
    assert dq["can_continue"] is False


def test_partial_when_optional_gaps(monkeypatch):
    # no supporting doc + KYC not completed + occupation missing -> only-optional gaps
    cust = {"customer_id": "C1", "occupation": None, "declared_income": 8000,
            "kyc_status": "Pending"}
    dq = _run(monkeypatch, cust, TXNS, alert={"supporting_document": None})
    assert dq["severity"] == "PARTIAL"
    assert dq["can_continue"] is True          # proceeds...
    assert dq["complete"] is False             # ...but flagged
    assert "manual" in dq["recommended_action"].lower()
    assert dq["quality_score"] < 85


def test_single_optional_gap_stays_good(monkeypatch):
    # only a missing supporting invoice shouldn't drop below GOOD
    dq = _run(monkeypatch, FULL_CUST, TXNS, alert={"supporting_document": None})
    assert dq["severity"] == "GOOD"
