"""
The SAR draft is a structured 12-section regulator-style package, framed as a
DRAFT (human review required) -- not an automatic STR submission.
"""

from app.agents.stage5_reporting.sar_drafting import sar_drafting
from app.services.sar_render import sar_to_markdown, sar_to_sections

EXPECTED_SECTIONS = [
    "case_information", "customer_information", "alert_trigger",
    "transaction_timeline", "suspicious_indicators", "kyc_review",
    "watchlist_screening", "policy_references", "risk_assessment",
    "ai_recommendation", "human_analyst_decision", "attachments",
]


def _state():
    return {
        "alert": {"id": "AML-2026-001", "customer_id": "CUST-10291",
                  "reason": "Structuring", "recipient": "Global Trade Ltd",
                  "country": "Malaysia", "total_amount": 39200, "num_transactions": 4},
        "triage": {"alert_type": "Structuring", "priority": "P1"},
        "transaction_findings": {"typology": "structuring", "summary": "Repeated sub-threshold transfers."},
        "kyc_findings": {"consistency": "inconsistent", "key_concern": "income mismatch",
                         "checks_failed": ["income_mismatch"], "edd_required": True},
        "watchlist_findings": {"verdict": "Possible match", "match_score": 88, "list_type": "INTERNAL_BLACKLIST",
                               "customer_screening": {"verdict": "NO_MATCH"},
                               "recipient_screening": {"verdict": "POSSIBLE_MATCH_REQUIRES_REVIEW"}},
        "retrieved_policies": [{"policy_id": "MY-STR-01", "title": "STR Lodgement",
                                "section": "3", "source": "SC"}],
        "risk_score": 90, "rule_score": 85, "ai_score": 92, "risk_level": "HIGH",
        "key_drivers": ["structuring"], "risk_explanation": "Sub-threshold structuring.",
        "risk_factors": [{"name": "Structuring", "evidence": "4 transfers near RM9,800"}],
        "recommendation": "Escalate for STR determination.",
    }


def test_sar_package_has_all_twelve_sections():
    out = sar_drafting.run(_state())
    pkg = out["sar_package"]
    for key in EXPECTED_SECTIONS:
        assert key in pkg, f"missing section: {key}"
    # framed as a draft, never an auto-submission
    assert pkg["ai_recommendation"]["human_review_required"] is True
    assert "DRAFT" in pkg["case_information"]["status"]


def test_sar_package_grounded_in_state():
    pkg = sar_drafting.run(_state())["sar_package"]
    assert pkg["transaction_timeline"]                       # built from transactions
    assert pkg["policy_references"][0]["policy_id"] == "MY-STR-01"
    assert pkg["risk_assessment"]["risk_level"] == "HIGH"
    # LLM mocked to "{}" -> indicators fall back to the triggered rules
    assert any("Structuring" in i for i in pkg["suspicious_indicators"])


def test_markdown_renders_numbered_sections():
    pkg = sar_drafting.run(_state())["sar_package"]
    md = sar_to_markdown(pkg)
    assert "# Suspicious Activity Report (DRAFT)" in md
    assert "## 1. Case Information" in md
    assert "## 12. Attachments / Supporting Evidence" in md
    assert "FIED" in md                                      # the STR disclaimer
    assert len(sar_to_sections(pkg)) == 12
