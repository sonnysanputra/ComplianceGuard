"""
Economic purpose / source-of-funds:
 - an unclear-purpose high-risk overseas transfer raises risk (a new rule)
 - a clear purpose + source + invoice supports a false-positive clearance
"""

from app.rules.rule_engine import evaluate_aml_rules, purpose_is_clear
from app.agents.false_positive_review import false_positive_review

CUST = {"customer_id": "C1", "declared_income": 8000, "previous_alerts": 0}


def _txn(tid, country, purpose=None, source=None, doc=None):
    return {"transaction_id": tid, "amount": 9000, "date_time": "2026-06-22T10:00:00",
            "recipient": "Overseas Co", "country": country, "transaction_type": "transfer",
            "is_new_recipient": True, "direction": "out",
            "transaction_purpose": purpose, "source_of_funds": source,
            "supporting_document_url": doc, "relationship_to_recipient": None}


def test_purpose_is_clear_helper():
    assert purpose_is_clear("Monthly hosting subscription")
    assert not purpose_is_clear(None)
    assert not purpose_is_clear("unknown")
    assert not purpose_is_clear("  Other ")


def test_unclear_purpose_high_risk_transfer_fires():
    # Cambodia is high-risk; no stated purpose -> AML-PURPOSE-001 should fire
    txns = [_txn("T1", "Cambodia", purpose=None)]
    result = evaluate_aml_rules(CUST, txns, {}, {}, {"total_amount": 9000})
    ids = [r.rule_id for r in result.triggered_rules]
    assert "AML-PURPOSE-001" in ids


def test_clear_purpose_does_not_fire_unclear_rule():
    txns = [_txn("T1", "Cambodia", purpose="Documented equipment import")]
    result = evaluate_aml_rules(CUST, txns, {}, {}, {"total_amount": 9000})
    ids = [r.rule_id for r in result.triggered_rules]
    assert "AML-PURPOSE-001" not in ids


def test_fp_review_uses_economic_purpose(monkeypatch):
    import app.agents.false_positive_review as fp
    documented = [_txn("T1", "Malaysia", purpose="Monthly cloud hosting",
                       source="Business revenue", doc="https://x/inv.pdf")]
    monkeypatch.setattr(fp, "get_customer", lambda cid: CUST)
    monkeypatch.setattr(fp, "get_transactions", lambda cid: documented)
    state = {"alert": {"customer_id": "C1", "recipient": "Overseas Co", "total_amount": 9000,
                       "reason": "supplier payment"},
             "watchlist_findings": {"is_match": False}, "kyc_findings": {"consistency": "consistent"}}
    fpr = false_positive_review.run(state)["fp_review"]
    assert fpr["checks"]["economic_purpose_clear"] is True
    assert fpr["checks"]["source_of_funds_known"] is True
