"""
Structured evidence: agents emit EvidenceItems, and every risk factor references
evidence by ID -- reusing the IDs upstream agents already minted (traceability).
"""

from app.core.evidence import EvidenceItem, EvidenceCollector, index_evidence
from app.agents.stage2_investigation.transaction_analysis import transaction_analysis
from app.agents.stage2_investigation.kyc_profile import kyc_profile
from app.agents.stage3_scoring.risk_scoring import risk_scoring


def test_collector_mints_readable_ids_and_dedupes():
    c = EvidenceCollector()
    a = c.add("transaction", "TXN-1", "amount", 9800, "near threshold")
    b = c.add("transaction", "TXN-1", "amount", 9800, "near threshold")   # same fact
    d = c.add("customer_profile", "CUST-1", "declared_income", 4000, "low income")
    assert a == "EV-TXN-001" and a == b          # deduped
    assert d == "EV-CUST-001"
    assert len(c.items) == 2
    EvidenceItem(**c.items[0])                    # validates against the schema


def test_evidence_item_schema_matches_spec():
    item = EvidenceItem(evidence_id="EV-TXN-001", source_type="transaction",
                        source_id="TXN-8821", field="amount", value=9800,
                        description="Transfer amount is close to internal review threshold.")
    assert item.value == 9800 and item.source_type == "transaction"


def test_agents_emit_structured_evidence():
    alert = {"id": "AML-T", "customer_id": "CUST-10291", "reason": "Structuring",
             "recipient": "Global Trade Ltd", "country": "Malaysia", "total_amount": 29400}
    tx = transaction_analysis.run({"alert": alert})
    assert tx["evidence"] and all("evidence_id" in e for e in tx["evidence"])
    assert tx["transaction_findings"]["evidence_ids"]


def test_risk_factors_reference_evidence_ids():
    alert = {"id": "AML-T", "customer_id": "CUST-10291", "reason": "Structuring",
             "recipient": "Global Trade Ltd", "country": "Cambodia", "total_amount": 29400}
    # upstream evidence already in the pool (as it would be at fan-in)
    upstream = transaction_analysis.run({"alert": alert})["evidence"]
    state = {
        "alert": alert,
        "kyc_findings": {"income_mismatch": True, "previous_alerts": 0,
                         "consistency": "inconsistent", "edd_required": True,
                         "checks_failed": ["income_mismatch"]},
        "watchlist_findings": {"is_match": False, "high_risk_country": False},
        "memory_findings": {}, "retrieved_policies": [], "evidence": upstream,
    }
    out = risk_scoring.run(state)
    factors = out["risk_factors"]
    assert factors, "expected at least one triggered factor"
    for f in factors:
        assert f.get("factor")                       # explicit factor label
        assert f.get("evidence_ids"), f"factor {f['name']} has no evidence_ids"
    # at least one factor should reference an ID minted upstream (not re-minted)
    upstream_ids = {e["evidence_id"] for e in upstream}
    all_ref = {eid for f in factors for eid in f["evidence_ids"]}
    assert all_ref & upstream_ids, "factors should reuse upstream evidence IDs"
