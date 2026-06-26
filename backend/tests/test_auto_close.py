"""
Auto-close emits a professional clearance note (reason + evidence + recommended
action) for both the cleared-false-positive and the clean-low-risk paths.
"""

import app.agents.stage4_disposition.auto_close as ac
from app.agents.stage4_disposition.auto_close import auto_close


def test_cleared_false_positive_note(monkeypatch):
    txns = [{"recipient": "Supplier ABC", "amount": 5000, "is_new_recipient": False,
             "supporting_document_url": "https://x/inv.pdf"}]
    monkeypatch.setattr(ac, "get_transactions", lambda cid: txns)
    state = {
        "alert": {"customer_id": "C1", "recipient": "Supplier ABC", "supporting_document": "INV-1"},
        "fp_review": {"requires_human_review": False, "clearance_reason": "Regular supplier payment.",
                      "checks": {"economic_purpose_clear": True, "amount_consistent": True}},
        "watchlist_findings": {"is_match": False},
        "adverse_media_findings": {"negative_news": False},
        "risk_factors": [{"name": "Volume Spike"}],
    }
    note = auto_close.run(state)["clearance_note"]
    assert note["status"] == "LOW_RISK_AUTO_CLEARED"
    assert note["clearance_reason"] == "Regular supplier payment."
    assert note["recommended_action"] == "Close with monitoring"   # FP path keeps monitoring
    ev = note["evidence"]
    assert any("Recipient has been paid" in e for e in ev)
    assert any("invoice" in e.lower() or "Supporting document" in e for e in ev)
    assert "No watchlist or sanctions match" in ev
    assert "Clear economic purpose stated" in ev


def test_clean_low_risk_note(monkeypatch):
    monkeypatch.setattr(ac, "get_transactions", lambda cid: [])
    state = {
        "alert": {"customer_id": "C2", "recipient": "Landlord"},
        "watchlist_findings": {"is_match": False},
        "adverse_media_findings": {"negative_news": False},
        "risk_factors": [],          # nothing triggered
    }
    note = auto_close.run(state)["clearance_note"]
    assert note["status"] == "LOW_RISK_AUTO_CLEARED"
    assert note["recommended_action"] == "Close - no further action required"
    assert any("No AML typology detected" in e for e in note["evidence"])
    assert "No adverse media found" in note["evidence"]


def test_note_always_has_evidence(monkeypatch):
    monkeypatch.setattr(ac, "get_transactions", lambda cid: [])
    state = {"alert": {"customer_id": "C3", "recipient": "X"}}
    note = auto_close.run(state)["clearance_note"]
    assert note["evidence"]                       # never empty
