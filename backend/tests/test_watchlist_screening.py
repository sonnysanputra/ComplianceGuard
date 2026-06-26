from app.agents.stage2_investigation.watchlist_screening import watchlist_screening


def test_recipient_screening_flags_blacklist_near_match():
    out = watchlist_screening.run({"alert": {"customer_id": "CUST-10291",
                                             "recipient": "Global Trade Ltd",
                                             "country": "Cambodia"}})
    f = out["watchlist_findings"]
    rec = f["recipient_screening"]
    assert rec["best_match"] == "Global Trade Limited"          # caught the near-match
    assert rec["list_type"] == "INTERNAL_BLACKLIST"
    assert rec["verdict"] == "POSSIBLE_MATCH_REQUIRES_REVIEW"
    assert "Manual verification" in f["required_action"]
    assert f["high_risk_country"] is True


def test_customer_clean_no_match():
    out = watchlist_screening.run({"alert": {"customer_id": "CUST-20555",
                                             "recipient": "Supplier ABC Sdn Bhd",
                                             "country": "Malaysia"}})
    f = out["watchlist_findings"]
    assert f["customer_screening"]["verdict"] == "NO_MATCH"
    assert f["recipient_screening"]["verdict"] == "NO_MATCH"
    assert f["is_match"] is False


def test_screens_both_parties():
    out = watchlist_screening.run({"alert": {"customer_id": "CUST-10291",
                                             "recipient": "x", "country": "Malaysia"}})
    f = out["watchlist_findings"]
    assert "customer_screening" in f and "recipient_screening" in f
    assert set(f["screened_parties"]) == {"customer", "recipient"}
