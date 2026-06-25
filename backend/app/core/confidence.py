"""
Confidence calibration.

An LLM saying "confidence 87%" is not credible on its own. Real confidence in a
risk decision depends on OBJECTIVE signals: how complete the data was, whether a
governing policy was found, whether any screening tool failed, and how strong the
transaction evidence is.

This starts from a base confidence and adjusts it by those signals, returning a
calibrated score plus the human-readable factors behind it.
"""


def calibrate_confidence(state: dict, base: float = 0.85) -> tuple[float, list[str]]:
    """Return (calibrated_confidence 0..1, confidence_factors)."""
    confidence = float(base)
    factors: list[str] = []

    # --- data quality ---
    dq = state.get("data_quality") or {}
    q = dq.get("quality_score", 100)
    if q < 70:
        confidence -= 0.20
        factors.append(f"Low data quality ({q}/100)")
    else:
        factors.append("KYC profile / data available")

    # --- governing policy retrieved? ---
    if state.get("retrieved_policies"):
        factors.append("Policy citation found")
    else:
        confidence -= 0.15
        factors.append("No policy citation found")

    # --- screening tool reliability ---
    errors = state.get("errors") or []
    if any(e.get("agent") == "watchlist_screening" for e in errors):
        confidence -= 0.30
        factors.append("Watchlist tool failed")
    else:
        wf = state.get("watchlist_findings") or {}
        if wf.get("is_match"):
            factors.append("Confirmed watchlist match")
        elif any((wf.get(p) or {}).get("verdict") == "POSSIBLE_MATCH_REQUIRES_REVIEW"
                 for p in ("customer_screening", "recipient_screening")):
            factors.append("Watchlist result is only a fuzzy match")

    # --- transaction evidence strength ---
    tf = state.get("transaction_findings") or {}
    strong = (tf.get("typology") not in (None, "none", "")
              or len(state.get("risk_factors") or []) >= 3)
    if strong:
        confidence += 0.10
        factors.append("Strong transaction evidence")
    else:
        factors.append("Limited transaction evidence")

    return round(max(0.0, min(confidence, 1.0)), 2), factors
