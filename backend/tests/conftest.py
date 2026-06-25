"""
Shared test fixtures.

The agents normally call the Qwen LLM (Ollama) and Supabase. For fast, reliable,
offline tests we mock both: the LLM returns empty JSON (so each agent falls back
to its DETERMINISTIC logic -- exactly the part we want to assert), and the DB
functions return controlled in-memory sample data mirroring the seed schema.
"""

import pytest

# ---- Sample data (mirrors backend/schema.sql) ----
CUSTOMERS = {
    "CUST-10291": {"customer_id": "CUST-10291", "name": "Aiman Rahman",
                   "occupation": "Junior Clerk", "declared_income": 4000,
                   "kyc_status": "Completed", "risk_category": "Medium",
                   "account_age_months": 14, "country": "Malaysia", "previous_alerts": 1},
    "CUST-20555": {"customer_id": "CUST-20555", "name": "Sarah Lim",
                   "occupation": "Business Owner", "declared_income": 45000,
                   "kyc_status": "Completed", "risk_category": "Low",
                   "account_age_months": 60, "country": "Malaysia", "previous_alerts": 0},
    "CUST-30877": {"customer_id": "CUST-30877", "name": "Daniel Tan",
                   "occupation": "Student", "declared_income": 1500,
                   "kyc_status": "Completed", "risk_category": "High",
                   "account_age_months": 4, "country": "Malaysia", "previous_alerts": 2},
    "CUST-40233": {"customer_id": "CUST-40233", "name": "Priya Nair",
                   "occupation": "Freelancer", "declared_income": 6000,
                   "kyc_status": "Completed", "risk_category": "Medium",
                   "account_age_months": 22, "country": "Malaysia", "previous_alerts": 0},
    "CUST-50001": {"customer_id": "CUST-50001", "name": "Tech Solutions Sdn Bhd",
                   "occupation": "Business Owner", "declared_income": 30000,
                   "kyc_status": "Completed", "risk_category": "Low",
                   "account_age_months": 36, "country": "Malaysia", "previous_alerts": 0},
}


_tx_seq = [0]


def _tx(amount, t, recipient, country, new, direction, purpose=None, source=None):
    _tx_seq[0] += 1
    return {"transaction_id": f"TXN-{8800 + _tx_seq[0]}",
            "amount": amount, "date_time": t, "recipient": recipient,
            "country": country, "transaction_type": "transfer",
            "is_new_recipient": new, "direction": direction,
            "transaction_purpose": purpose, "source_of_funds": source,
            "supporting_document_url": None, "relationship_to_recipient": None}


TRANSACTIONS = {
    # structuring: 3x just under RM10k, overseas, new recipient
    "CUST-10291": [
        _tx(9800, "2026-06-22T09:15:00", "Global Trade Ltd", "Cambodia", True, "out"),
        _tx(9800, "2026-06-22T11:40:00", "Global Trade Ltd", "Cambodia", True, "out"),
        _tx(9800, "2026-06-22T14:55:00", "Global Trade Ltd", "Cambodia", True, "out"),
        _tx(120, "2026-05-03T12:00:00", "Speedmart", "Malaysia", False, "out"),
        _tx(300, "2026-05-10T18:30:00", "TNB", "Malaysia", False, "out"),
        _tx(250, "2026-05-20T09:00:00", "Mama Rahman", "Malaysia", False, "out"),
    ],
    # false positive: large but to a KNOWN supplier (not new)
    "CUST-20555": [
        _tx(18000, "2026-04-15T10:00:00", "Supplier ABC Sdn Bhd", "Malaysia", False, "out"),
        _tx(22000, "2026-05-15T10:00:00", "Supplier ABC Sdn Bhd", "Malaysia", False, "out"),
        _tx(20000, "2026-06-22T10:00:00", "Supplier ABC Sdn Bhd", "Malaysia", False, "out"),
    ],
    # money mule: large inbound rapidly forwarded out to new recipients
    "CUST-30877": [
        _tx(200, "2026-06-01T12:00:00", "Cafe", "Malaysia", False, "out"),
        _tx(48000, "2026-06-21T10:00:00", "Overseas Holdings", "Malaysia", True, "in"),
        _tx(11500, "2026-06-21T12:30:00", "Recipient One", "Malaysia", True, "out"),
        _tx(11500, "2026-06-21T13:10:00", "Recipient Two", "Malaysia", True, "out"),
        _tx(11500, "2026-06-21T15:45:00", "Recipient Three", "Malaysia", True, "out"),
        _tx(11500, "2026-06-21T17:20:00", "Recipient Four", "Malaysia", True, "out"),
    ],
    # layering / dispersion: split across many new recipients in a day
    "CUST-40233": [
        _tx(500, "2026-06-05T09:00:00", "Grab", "Malaysia", False, "out"),
        *[_tx(3000, f"2026-06-20T{9+i:02d}:05:00", f"Beneficiary {chr(65+i)}",
              "Malaysia", True, "out") for i in range(8)],
    ],
    # documented supplier payment: volume flag, but a new well-documented recipient
    "CUST-50001": [
        _tx(1500, "2026-05-02T10:00:00", "AWS Cloud", "Malaysia", False, "out"),
        _tx(1800, "2026-05-18T10:00:00", "Office Rental", "Malaysia", False, "out"),
        _tx(20000, "2026-06-22T10:00:00", "CloudHost Services", "Malaysia", True, "out",
            purpose="Monthly cloud hosting subscription", source="Business operating revenue"),
    ],
}

WATCHLIST = [
    {"id": 1, "entity_name": "Global Trade Limited", "entity_type": "company",
     "list_type": "INTERNAL_BLACKLIST", "risk_level": "High"},
    {"id": 2, "entity_name": "Ahmad Zulkifli", "entity_type": "individual",
     "list_type": "PEP", "risk_level": "High"},
    {"id": 3, "entity_name": "Northern Star Holdings", "entity_type": "company",
     "list_type": "UN_SANCTIONS", "risk_level": "Critical"},
]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Replace LLM + DB calls so tests run offline and deterministically."""
    monkeypatch.setattr("app.agents.base.chat",
                        lambda prompt, system=None, temperature=0.2: "{}")
    monkeypatch.setattr("app.agents.transaction_analysis.get_transactions",
                        lambda cid: TRANSACTIONS.get(cid, []))
    monkeypatch.setattr("app.agents.transaction_timeline.get_transactions",
                        lambda cid: TRANSACTIONS.get(cid, []))
    monkeypatch.setattr("app.agents.kyc_profile.get_customer", lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.risk_scoring.get_customer", lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.risk_scoring.get_transactions",
                        lambda cid: TRANSACTIONS.get(cid, []))
    monkeypatch.setattr("app.agents.watchlist_screening.get_customer", lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.watchlist_screening.get_watchlist", lambda: WATCHLIST)
    monkeypatch.setattr("app.agents.case_memory.get_customer", lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.case_memory.get_customer_history",
                        lambda cid, exclude_case_id="": {"cases": [], "decisions": []})
    monkeypatch.setattr("app.agents.data_quality.get_customer", lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.data_quality.get_transactions",
                        lambda cid: TRANSACTIONS.get(cid, []))
    monkeypatch.setattr("app.agents.false_positive_review.get_customer",
                        lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.false_positive_review.get_transactions",
                        lambda cid: TRANSACTIONS.get(cid, []))
    monkeypatch.setattr("app.agents.sar_drafting.get_customer", lambda cid: CUSTOMERS.get(cid))
    monkeypatch.setattr("app.agents.sar_drafting.get_transactions",
                        lambda cid: TRANSACTIONS.get(cid, []))
