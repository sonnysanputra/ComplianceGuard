"""
The false-positive review either auto-closes a clearly benign case, or refers it
to a human -- and a sanctions/blacklist name match is NEVER auto-cleared.
"""

from app.agents.false_positive_review import false_positive_review


def _state(alert, watchlist=None, kyc=None):
    return {
        "alert": alert,
        "watchlist_findings": watchlist or {"is_match": False,
            "customer_screening": {"verdict": "NO_MATCH"},
            "recipient_screening": {"verdict": "NO_MATCH"}},
        "kyc_findings": kyc or {"consistency": "consistent", "edd_required": False},
    }


def test_documented_supplier_payment_auto_closes():
    alert = {"customer_id": "CUST-50001", "recipient": "CloudHost Services",
             "total_amount": 20000, "reason": "supplier payment",
             "supporting_document": "INV-2026-552"}
    out = false_positive_review.run(_state(alert))
    fp = out["fp_review"]
    assert fp["checks"]["supporting_document_exists"] is True
    assert fp["checks"]["no_watchlist_match"] is True
    assert fp["requires_human_review"] is False          # cleared -> auto-close
    assert fp["recommended_action"] == "Auto-close with audit note."


def test_sanctions_name_match_always_needs_human():
    alert = {"customer_id": "CUST-50001", "recipient": "Northern Star Trading",
             "total_amount": 12000, "reason": "supplier payment",
             "supporting_document": "INV-2026-900"}
    wl = {"is_match": False, "list_type": "UN_SANCTIONS",
          "customer_screening": {"verdict": "NO_MATCH"},
          "recipient_screening": {"verdict": "POSSIBLE_MATCH_REQUIRES_REVIEW"}}
    out = false_positive_review.run(_state(alert, watchlist=wl))
    fp = out["fp_review"]
    assert fp["requires_human_review"] is True           # sanctions match -> never auto-cleared
    assert "verification" in fp["recommended_action"].lower()
