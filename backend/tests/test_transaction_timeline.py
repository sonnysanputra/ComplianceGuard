"""
The transaction timeline is chronological and annotates each event with a
plain-language risk note an analyst can read top-to-bottom.

The timeline is now built inside the Transaction Analysis Agent (it folds in the
former standalone Timeline Agent), so we assert on its `timeline_findings` output.
"""

from app.agents.stage2_investigation.transaction_analysis import transaction_analysis


def _run(cid):
    return transaction_analysis.run({"alert": {"customer_id": cid}})["timeline_findings"]


def test_timeline_is_chronological():
    tl = _run("CUST-10291")["timeline"]
    times = [e["time"] for e in tl]
    assert times == sorted(times)


def test_structuring_notes_first_overseas_then_near_threshold():
    # CUST-10291: three RM9,800 transfers to a new Cambodia recipient (structuring)
    tl = _run("CUST-10291")["timeline"]
    overseas = [e for e in tl if e["country"] == "Cambodia"]
    assert overseas, "expected the overseas transfers"
    # the first overseas transfer is flagged as the new overseas recipient
    assert "First transfer to new" in overseas[0]["risk_note"]
    assert "overseas" in overseas[0]["risk_note"] or "high-risk" in overseas[0]["risk_note"]
    # later near-threshold transfers are numbered ("Second ...", "Third ...")
    assert any("near-threshold" in e["risk_note"] for e in overseas[1:])


def test_incoming_funds_flagged_as_inflow():
    # CUST-30877: RM48,000 incoming then forwarded (mule pattern)
    tl = _run("CUST-30877")["timeline"]
    incoming = [e for e in tl if e["direction"] == "IN"]
    assert incoming and "incoming" in incoming[0]["risk_note"].lower()


def test_notable_events_exclude_routine():
    f = _run("CUST-10291")
    assert f["notable_events"]
    assert all("Routine" not in n["risk_note"] for n in f["notable_events"])
