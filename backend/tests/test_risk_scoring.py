"""
Risk scoring now delegates deterministic detection to the AML rule engine, so
these tests drive it with the real sample customers + transactions.
"""

from app.agents.stage3_scoring.risk_scoring import risk_scoring


def _state(customer_id, is_match=False, high_risk_country=False, memory=None, errors=None):
    return {
        "alert": {"customer_id": customer_id, "total_amount": 0,
                  "country": "Cambodia", "num_transactions": 3},
        "kyc_findings": {"income_mismatch": False, "previous_alerts": 0,
                         "consistency": "x", "key_concern": "x", "edd_required": False},
        "watchlist_findings": {"is_match": is_match,
                               "high_risk_country": high_risk_country, "verdict": "x"},
        "memory_findings": memory or {},
        "retrieved_policies": [],
        "errors": errors or [],
    }


def test_structuring_customer_is_high_risk():
    out = risk_scoring.run(_state("CUST-10291", high_risk_country=True))
    assert out["risk_score"] >= 60
    assert out["risk_level"] in ("HIGH", "CRITICAL")
    assert out["risk_factors"]                      # triggered rules present
    assert any("STRUCT" in f["rule_id"] for f in out["risk_factors"])


def test_clean_customer_is_low_risk():
    out = risk_scoring.run(_state("CUST-20555"))
    assert out["risk_score"] < 60
    assert out["risk_level"] == "LOW"


def test_tool_failure_forces_manual_review():
    out = risk_scoring.run(_state("CUST-10291",
                                  errors=[{"agent": "watchlist_screening", "error": "down"}]))
    assert out["risk_level"] == "MANUAL_REVIEW_REQUIRED"
    assert out.get("sar_draft") is None     # never draft a SAR on bad data
