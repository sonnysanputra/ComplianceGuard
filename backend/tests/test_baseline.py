"""
Account behaviour baseline: derive the customer's normal pattern, then fire
deviation rules when the flagged activity strays from it.
"""

from app.core.baseline import compute_baseline, behavior_deviations
from app.rules.rule_engine import get_rules, evaluate_aml_rules

CFG = get_rules()["behavior_baseline"]


def _tx(tid, amount, dt, recipient, country, new, direction="out"):
    return {"transaction_id": tid, "amount": amount, "date_time": dt,
            "recipient": recipient, "country": country,
            "is_new_recipient": new, "direction": direction}


# established history: small local payments in May; then a big new overseas burst
HISTORY = [
    _tx("H1", 1000, "2026-02-01T10:00:00", "Supplier ABC", "Malaysia", False),
    _tx("H2", 1200, "2026-02-15T11:00:00", "Supplier ABC", "Malaysia", False),
    _tx("H3", 900,  "2026-03-01T12:00:00", "Landlord", "Malaysia", False),
]


def test_baseline_metrics():
    b = compute_baseline(HISTORY)
    assert b["max_single_transaction_90d"] == 1200
    assert b["usual_countries"] == ["Malaysia"]
    assert "Supplier ABC" in b["usual_recipients"]
    assert b["usual_transaction_hours"] == "10:00-12:00"


def test_amount_spike_and_new_country_fire():
    # a RM30,000 transfer to Cambodia, 6 months later (dormant), at 02:00
    txns = HISTORY + [_tx("R1", 30000, "2026-09-10T02:00:00", "New Co", "Cambodia", True)]
    devs = behavior_deviations(txns, {"customer_id": "C1"}, CFG)
    ids = {d["rule_id"] for d in devs}
    assert "AML-BEHAV-001" in ids                  # amount spike (30k > 5x 1200)
    assert "AML-BEHAV-002" in ids                  # new country (Cambodia)
    assert "AML-BEHAV-003" in ids                  # off hours (02:00)
    assert "AML-BEHAV-004" in ids                  # high-value new recipient
    assert "AML-BEHAV-005" in ids                  # dormant reactivation (~6 months)


def test_no_deviation_for_normal_activity():
    # a modest new local payment within usual hours, soon after history
    txns = HISTORY + [_tx("R1", 1100, "2026-03-05T11:00:00", "New Cafe", "Malaysia", True)]
    ids = {d["rule_id"] for d in behavior_deviations(txns, {"customer_id": "C1"}, CFG)}
    assert "AML-BEHAV-001" not in ids and "AML-BEHAV-002" not in ids
    assert "AML-BEHAV-005" not in ids


def test_deviations_feed_the_rule_engine():
    txns = HISTORY + [_tx("R1", 30000, "2026-09-10T02:00:00", "New Co", "Cambodia", True)]
    cust = {"customer_id": "C1", "declared_income": 5000, "previous_alerts": 0}
    result = evaluate_aml_rules(cust, txns, {}, {}, {"customer_id": "C1", "total_amount": 30000})
    behav = [r for r in result.triggered_rules if r.rule_id.startswith("AML-BEHAV")]
    assert behav, "behaviour deviation rules should appear in the engine output"
    assert all(r.evidence_items for r in behav)    # each carries traceable evidence
