"""
Golden test cases -- verify each AML typology is detected correctly.
These pin the core behaviour: the right pattern is recognised for each scenario.
"""

from app.agents.stage2_investigation.transaction_analysis import transaction_analysis


def _alert(cid, recipient="", country="Malaysia", n=0, amount=0):
    return {"alert": {"id": "T", "customer_id": cid, "reason": "x",
                      "recipient": recipient, "country": country,
                      "num_transactions": n, "total_amount": amount}}


def test_aml_2026_001_detects_structuring():
    out = transaction_analysis.run(
        _alert("CUST-10291", "Global Trade Ltd", "Cambodia", 3, 29400))
    assert out["transaction_findings"]["typology"] == "structuring"


def test_aml_2026_002_detects_money_mule():
    out = transaction_analysis.run(_alert("CUST-30877", n=4, amount=46000))
    assert out["transaction_findings"]["typology"] == "money mule"


def test_aml_2026_003_detects_layering_dispersion():
    out = transaction_analysis.run(_alert("CUST-40233", n=8, amount=24000))
    assert out["transaction_findings"]["typology"] == "layering/dispersion"


def test_aml_2026_004_no_suspicious_typology():
    out = transaction_analysis.run(
        _alert("CUST-20555", "Supplier ABC Sdn Bhd", "Malaysia", 1, 20000))
    assert out["transaction_findings"]["typology"] == "none"
