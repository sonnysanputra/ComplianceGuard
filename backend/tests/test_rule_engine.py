"""
The AML rule engine is pure (no DB / LLM), so it can be tested directly --
the clean separation the architecture is built around.
"""

from app.rules.rule_engine import detect_transaction_typology, evaluate_aml_rules


def _tx(amount, t, recipient, country="Malaysia", new=True, direction="out"):
    return {"amount": amount, "date_time": t, "recipient": recipient,
            "country": country, "transaction_type": "transfer",
            "is_new_recipient": new, "direction": direction}


STRUCTURING = [
    _tx(9800, "2026-06-22T09:00:00", "Acme", "Cambodia"),
    _tx(9800, "2026-06-22T11:00:00", "Acme", "Cambodia"),
    _tx(9800, "2026-06-22T14:00:00", "Acme", "Cambodia"),
]


def test_detects_structuring_typology():
    assert detect_transaction_typology(STRUCTURING)["typology"] == "structuring"


def test_evaluate_returns_triggered_rules_and_score():
    customer = {"declared_income": 4000, "previous_alerts": 1}
    result = evaluate_aml_rules(customer, STRUCTURING,
                                {"is_match": False, "high_risk_country": True}, {})
    assert result.total_rule_score > 0
    assert result.typology == "structuring"
    # the structuring rule fired, with full metadata
    rule = next(r for r in result.triggered_rules if r.rule_id == "AML-STRUCT-001")
    assert rule.severity == "HIGH"
    assert rule.points == 25
    assert "RM" in rule.evidence
    # serializes cleanly for the API/state
    d = result.to_dict()
    assert {"triggered_rules", "total_rule_score", "typology", "flags"} <= d.keys()


def test_clean_transactions_score_zero():
    clean = [_tx(200, "2026-06-01T10:00:00", "Known Supplier", new=False)]
    result = evaluate_aml_rules({"declared_income": 5000}, clean, {}, {})
    assert result.total_rule_score == 0
    assert result.typology == "none"
