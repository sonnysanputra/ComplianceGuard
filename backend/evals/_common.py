"""
Shared helpers for the evaluation suite.

Evals run the DETERMINISTIC layer (rule engine + typology + routing) over the
golden cases, so they are reproducible and require no live LLM or database. The
LLM is stubbed where an agent would call it, so false-positive review uses its
deterministic heuristic.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# stub the LLM so evals are offline + deterministic
import app.agents.base as _base                       # noqa: E402
_base.chat = lambda prompt, system=None, temperature=0.2: "{}"

from app.rules.rule_engine import detect_transaction_typology, evaluate_aml_rules  # noqa: E402
from app.rules.country_risk import is_high_risk        # noqa: E402


def load_cases() -> list[dict]:
    return json.loads((HERE / "golden_cases.json").read_text(encoding="utf-8"))


def _risk_level(score: int) -> str:
    return ("CRITICAL" if score >= 85 else "HIGH" if score >= 60
            else "MEDIUM" if score >= 35 else "LOW")


def build_state(case: dict) -> dict:
    """Run the deterministic pipeline for a golden case and return a state dict
    shaped like the live graph state (rule baseline drives the score)."""
    cust, txns, alert = case["customer"], case["transactions"], case["alert"]
    wf = case.get("watchlist_findings") or {
        "is_match": False,
        "customer_screening": {"verdict": "NO_MATCH"},
        "recipient_screening": {"verdict": "NO_MATCH"},
        "high_risk_country": is_high_risk(alert.get("country", "")),
        "verdict": "No watchlist match",
    }
    det = detect_transaction_typology(txns)
    result = evaluate_aml_rules(cust, txns, wf, {}, alert)
    score = result.total_rule_score
    factors = [r.to_dict() for r in result.triggered_rules]

    return {
        "alert": alert, "customer": cust, "transactions": txns,
        "transaction_findings": {"typology": det["typology"], "flags": det["flags"],
                                 "total_recent": det["total_recent"], "summary": "deterministic",
                                 "llm_red_flags": []},
        "watchlist_findings": wf,
        "kyc_findings": {"consistency": "consistent", "income_mismatch": False,
                         "previous_alerts": cust.get("previous_alerts", 0),
                         "edd_required": False, "checks_failed": []},
        "risk_score": score, "rule_score": score, "ai_score": score,
        "risk_level": _risk_level(score),
        "risk_factors": factors,
        "key_drivers": [r.name for r in result.triggered_rules[:3]],
        "recommendation": "Escalate" if score >= 60 else "Monitor",
        "risk_explanation": "Deterministic rule evaluation (golden eval).",
        "confidence": 0.9, "confidence_factors": ["golden eval"],
        "priority": "P1" if score >= 85 else "P2" if score >= 60 else "P3",
        "data_quality": {"quality_score": 100, "severity": "GOOD", "can_continue": True},
        "retrieved_policies": [],
        "typology": det["typology"],
    }


def route_label(state: dict) -> str:
    """The coarse route the fail-safe router would take for this state."""
    from langgraph.graph import END
    from app.orchestrator import route_after_scoring
    r = route_after_scoring(state)
    if r is END:
        return "AUTO_CLOSE"
    return {"sar_drafting": "SAR_DRAFTED", "human_approval": "MANUAL_REVIEW",
            "false_positive_review": "FALSE_POSITIVE_REVIEW",
            "auto_close": "AUTO_CLOSE"}.get(r, str(r))


def pct(n: int, d: int) -> str:
    return f"{(100 * n / d):.0f}%" if d else "n/a"
