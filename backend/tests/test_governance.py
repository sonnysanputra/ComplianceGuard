"""
Model governance: every agent output records which model / prompt / ruleset /
policy version produced it, so any decision can be reproduced and audited.
"""

from app.core.governance import governance, model_name, ruleset_version
from app.agents.stage3_scoring.risk_scoring import risk_scoring
from app.agents.stage2_investigation.watchlist_screening import watchlist_screening


def test_governance_metadata_shape():
    g = governance("risk_scoring_v1.2", uses_llm=True)
    assert g["model_name"] == "qwen2.5:7b"
    assert g["prompt_version"] == "risk_scoring_v1.2"
    assert g["ruleset_version"] == "aml_rules_2026_06"
    assert g["policy_version"] and g["policy_version"].startswith("policy_")


def test_deterministic_agent_has_no_model():
    g = governance("watchlist_screening_v1", uses_llm=False)
    assert g["model_name"] is None
    # version metadata is still recorded for deterministic agents
    assert g["ruleset_version"] == "aml_rules_2026_06"


def test_trace_carries_governance():
    tr = risk_scoring.trace("rationale", 0.8)
    assert tr["model_name"] == "qwen2.5:7b"
    assert tr["prompt_version"] == "risk_scoring_v1.2"     # the agent's declared version
    assert tr["ruleset_version"] == "aml_rules_2026_06"
    assert "policy_version" in tr


def test_deterministic_agent_trace_model_is_none():
    tr = watchlist_screening.trace("rationale", 0.9)
    assert tr["model_name"] is None
    assert tr["prompt_version"] == "watchlist_screening_v1"  # default <name>_v1


def test_ruleset_and_model_helpers():
    assert model_name() == "qwen2.5:7b"
    assert ruleset_version() == "aml_rules_2026_06"
