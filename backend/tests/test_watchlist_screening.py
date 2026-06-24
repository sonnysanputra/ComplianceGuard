from app.agents.watchlist_screening import watchlist_screening


def test_fuzzy_matches_similar_blacklisted_entity():
    out = watchlist_screening.run({"alert": {"customer_id": "CUST-10291",
                                             "recipient": "Global Trade Ltd",
                                             "country": "Cambodia"}})
    f = out["watchlist_findings"]
    assert f["best_match"] == "Global Trading Limited"   # caught the near-match
    assert f["match_score"] >= 70                         # surfaced for review
    assert f["high_risk_country"] is True


def test_clean_recipient_no_match():
    out = watchlist_screening.run({"alert": {"customer_id": "CUST-20555",
                                             "recipient": "Supplier ABC Sdn Bhd",
                                             "country": "Malaysia"}})
    f = out["watchlist_findings"]
    assert f["is_match"] is False
    assert f["high_risk_country"] is False


def test_screens_both_parties():
    out = watchlist_screening.run({"alert": {"customer_id": "CUST-10291",
                                             "recipient": "x", "country": "Malaysia"}})
    assert set(out["watchlist_findings"]["screened_parties"]) == {"customer", "recipient"}
