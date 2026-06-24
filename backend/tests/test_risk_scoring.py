from app.agents.risk_scoring import risk_scoring

ALL_FLAGS = ["money_mule", "structuring", "rapid_dispersion",
             "new_overseas_recipient", "volume_spike"]


def _state(flags=None, income_mismatch=False, watchlist=False, hrc=False,
           prior_alerts=0, errors=None):
    base = {f: False for f in ALL_FLAGS}
    base.update(flags or {})
    return {
        "alert": {"country": "Cambodia", "num_transactions": 3},
        "transaction_findings": {"flags": base, "typology": "x",
                                 "total_recent": 29400, "window_hours": 6,
                                 "distinct_recipients": 1},
        "kyc_findings": {"income_mismatch": income_mismatch, "previous_alerts": prior_alerts,
                         "burst_total": 29400, "declared_income": 4000, "income_ratio": 7.3},
        "watchlist_findings": {"is_match": watchlist, "high_risk_country": hrc, "verdict": "x"},
        "memory_findings": {}, "retrieved_policies": [], "errors": errors or [],
    }


def test_structuring_case_is_high_risk():
    out = risk_scoring.run(_state(
        flags={"structuring": True, "new_overseas_recipient": True, "volume_spike": True},
        income_mismatch=True, hrc=True, prior_alerts=1))
    assert out["risk_score"] >= 60
    assert out["risk_level"] in ("HIGH", "CRITICAL")


def test_clean_case_is_low_risk():
    out = risk_scoring.run(_state())
    assert out["risk_score"] < 60
    assert out["risk_level"] == "LOW"


def test_tool_failure_forces_manual_review():
    out = risk_scoring.run(_state(errors=[{"agent": "watchlist_screening", "error": "down"}]))
    assert out["risk_level"] == "MANUAL_REVIEW_REQUIRED"
    assert out.get("sar_draft") is None        # never draft a SAR on bad data
