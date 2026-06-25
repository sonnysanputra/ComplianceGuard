"""
Relationship-graph analysis: detects layering (fan-out + forwarding + a common
collector) and money-mule (rapid in->out forwarding) money-flow patterns.
"""

from app.tools.graph_analysis import analyze_graph, analyze_account, transactions_to_edges
from app.rules.rule_engine import evaluate_aml_rules

# a layering/dispersion network: fan-out to 8, with A and B forwarding to a
# common collector D
LAYERING_EDGES = (
    [{"from": "CUST-40233", "to": f"Beneficiary {c}", "amount": 3000,
      "time": f"2026-06-20T{9 + i:02d}:05:00"} for i, c in enumerate("ABCDEFGH")]
    + [{"from": "Beneficiary A", "to": "Beneficiary D", "amount": 2900, "time": "2026-06-20T17:30:00"},
       {"from": "Beneficiary B", "to": "Beneficiary D", "amount": 2900, "time": "2026-06-20T18:00:00"}]
)


def test_layering_network_features():
    g = analyze_graph(LAYERING_EDGES, "CUST-40233")
    assert g["fan_out_count"] == 8
    assert g["rapid_forwarding_detected"] is True
    assert "Beneficiary D" in g["common_recipient"]
    # the layering path starts at the root and reaches the collector
    assert g["possible_layering_path"][0] == "CUST-40233"
    assert g["possible_layering_path"][-1] == "Beneficiary D"
    assert g["graph_risk_score"] == 25            # fan-out(10) + rapid(10) + common(5)


def test_mule_rapid_forwarding_from_transactions():
    # incoming, then four rapid onward transfers -> rapid forwarding
    txns = [{"amount": 48000, "date_time": "2026-06-21T10:00:00", "recipient": "Overseas Co",
             "is_new_recipient": True, "direction": "in"}]
    txns += [{"amount": 11500, "date_time": f"2026-06-21T{12 + i}:00:00",
              "recipient": f"Recipient {i}", "is_new_recipient": True, "direction": "out"}
             for i in range(4)]
    g = analyze_account("CUST-30877", txns, edges=[])
    assert g["fan_in_count"] == 1
    assert g["rapid_forwarding_detected"] is True


def test_clean_account_has_no_network_risk():
    txns = [{"amount": 300, "date_time": "2026-06-01T10:00:00", "recipient": "Cafe",
             "is_new_recipient": False, "direction": "out"}]
    g = analyze_account("CUST-1", txns, edges=[])
    assert g["graph_risk_score"] == 0
    assert g["rapid_forwarding_detected"] is False


def test_db_edges_preferred_over_transactions():
    # even with no transactions, the edge table drives the analysis
    g = analyze_account("CUST-40233", transactions=[], edges=LAYERING_EDGES)
    assert g["fan_out_count"] == 8


def test_graph_risk_feeds_rule_engine():
    cust = {"customer_id": "CUST-40233", "declared_income": 6000, "previous_alerts": 0}
    gf = analyze_graph(LAYERING_EDGES, "CUST-40233")
    result = evaluate_aml_rules(cust, [], {}, {}, {"total_amount": 24000}, graph=gf)
    hit = {r.rule_id: r for r in result.triggered_rules}.get("AML-GRAPH-001")
    assert hit and hit.points == 25
    assert hit.evidence_items
