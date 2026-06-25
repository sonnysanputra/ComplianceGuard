"""
Adverse media screening: negative news on the customer or recipient is found,
recorded as structured evidence, and raises the risk score.
"""

from app.tools.adverse_media import search_adverse_media
from app.agents.adverse_media_screening import adverse_media_screening
from app.rules.rule_engine import evaluate_aml_rules

CUST = {"customer_id": "C1", "name": "Acme Trading", "declared_income": 8000,
        "previous_alerts": 0}


def test_tool_finds_and_misses():
    hit = search_adverse_media("Global Trade Ltd")
    assert hit["verdict"] == "NEGATIVE_NEWS_FOUND"
    assert hit["hits"][0]["risk_level"] == "HIGH"

    clean = search_adverse_media("CloudHost Services")
    assert clean["verdict"] == "NO_ADVERSE_MEDIA" and clean["hits"] == []


def test_agent_screens_both_parties(monkeypatch):
    import app.agents.adverse_media_screening as am
    monkeypatch.setattr(am, "get_customer", lambda cid: CUST)
    state = {"alert": {"customer_id": "C1", "recipient": "Global Trade Ltd"}}
    out = adverse_media_screening.run(state)
    f = out["adverse_media_findings"]
    assert f["verdict"] == "NEGATIVE_NEWS_FOUND"
    assert f["hit_count"] == 1 and f["highest_risk_level"] == "HIGH"
    # structured, traceable evidence was emitted
    assert out["evidence"] and out["evidence"][0]["source_type"] == "adverse_media"
    assert f["evidence_ids"]


def test_no_news_is_clean(monkeypatch):
    import app.agents.adverse_media_screening as am
    monkeypatch.setattr(am, "get_customer", lambda cid: CUST)
    state = {"alert": {"customer_id": "C1", "recipient": "CloudHost Services"}}
    f = adverse_media_screening.run(state)["adverse_media_findings"]
    assert f["verdict"] == "NO_ADVERSE_MEDIA" and f["negative_news"] is False


def test_adverse_media_raises_risk_score():
    am = {"negative_news": True, "highest_risk_level": "HIGH", "hit_count": 1,
          "all_hits": [{"name": "Global Trade Ltd", "title": "invoice fraud", "risk_level": "HIGH"}]}
    result = evaluate_aml_rules(CUST, [], {}, {}, {"total_amount": 5000}, am)
    fired = {r.rule_id: r for r in result.triggered_rules}
    assert "AML-ADVMEDIA-001" in fired
    assert fired["AML-ADVMEDIA-001"].points == 20
    # a CRITICAL hit is weighted higher
    am["highest_risk_level"] = "CRITICAL"
    result = evaluate_aml_rules(CUST, [], {}, {}, {"total_amount": 5000}, am)
    assert {r.rule_id: r for r in result.triggered_rules}["AML-ADVMEDIA-001"].points == 30
