"""
Confidence is calibrated from objective signals (data quality, policy, tool
failures, evidence strength) -- not taken at face value from the LLM.
"""

from app.core.confidence import calibrate_confidence


def test_strong_case_high_confidence():
    state = {
        "data_quality": {"quality_score": 100},
        "retrieved_policies": [{"policy_id": "MY-STR-01"}],
        "watchlist_findings": {"is_match": True},
        "transaction_findings": {"typology": "structuring"},
        "risk_factors": [{}, {}, {}],
    }
    conf, factors = calibrate_confidence(state, base=0.85)
    assert conf >= 0.9                              # base 0.85 + strong evidence 0.10 -> capped
    assert "Strong transaction evidence" in factors
    assert "Policy citation found" in factors
    assert "Confirmed watchlist match" in factors


def test_each_deduction_applies():
    state = {
        "data_quality": {"quality_score": 60},      # -0.20
        "retrieved_policies": [],                    # -0.15
        "transaction_findings": {"typology": "none"},
        "risk_factors": [],                          # not strong: no +0.10
    }
    conf, factors = calibrate_confidence(state, base=0.85)
    assert conf == 0.50                             # 0.85 - 0.20 - 0.15
    assert "Low data quality (60/100)" in factors
    assert "No policy citation found" in factors
    assert "Limited transaction evidence" in factors


def test_watchlist_tool_failure_drops_confidence():
    state = {
        "data_quality": {"quality_score": 100},
        "retrieved_policies": [{"policy_id": "x"}],
        "errors": [{"agent": "watchlist_screening", "error": "timeout"}],
        "transaction_findings": {"typology": "structuring"},
    }
    conf, factors = calibrate_confidence(state, base=0.85)
    assert conf == 0.65                             # 0.85 - 0.30(tool) + 0.10(strong)
    assert "Watchlist tool failed" in factors


def test_fuzzy_match_is_noted():
    state = {
        "data_quality": {"quality_score": 100},
        "retrieved_policies": [{"policy_id": "x"}],
        "watchlist_findings": {"is_match": False,
            "recipient_screening": {"verdict": "POSSIBLE_MATCH_REQUIRES_REVIEW"}},
        "transaction_findings": {"typology": "none"},
    }
    _, factors = calibrate_confidence(state, base=0.85)
    assert "Watchlist result is only a fuzzy match" in factors


def test_confidence_is_clamped():
    conf, _ = calibrate_confidence({"errors": [{"agent": "watchlist_screening"}],
                                    "retrieved_policies": [], "data_quality": {"quality_score": 10}},
                                   base=0.5)
    assert conf == 0.0                             # cannot go below 0
