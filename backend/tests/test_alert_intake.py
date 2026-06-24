from app.agents.alert_intake import AlertIntakeAgent, alert_intake

_classify = AlertIntakeAgent._classify_type


def test_classifies_structuring():
    assert _classify("multiple transfers just under the reporting threshold") == "Structuring"


def test_classifies_money_mule():
    assert _classify("large incoming transfer rapidly forwarded to recipients") == "Money mule"


def test_classifies_layering():
    assert _classify("funds dispersed across many new recipients") == "Layering / dispersion"


def test_lone_threshold_is_not_structuring():
    assert _classify("high-value transfer flagged by amount threshold") == "Threshold-triggered alert"


def test_high_value_overseas_is_priority_1():
    out = alert_intake.run({"alert": {"id": "T", "customer_id": "C", "reason": "x",
                                      "recipient": "r", "country": "Cambodia",
                                      "total_amount": 29400, "num_transactions": 3}})
    assert out["triage"]["priority"] == "P1"
    assert out["triage"]["severity"] == "High"
