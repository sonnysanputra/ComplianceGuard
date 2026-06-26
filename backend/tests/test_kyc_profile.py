from app.agents.stage2_investigation.kyc_profile import kyc_profile


def test_student_moving_large_sums_triggers_edd():
    out = kyc_profile.run({"alert": {"customer_id": "CUST-30877", "total_amount": 46000}})
    f = out["kyc_findings"]
    assert f["income_mismatch"] is True
    assert "occupation_risk" in f["checks_failed"]        # a student
    assert "new_account_high_value" in f["checks_failed"]  # 4-month-old account
    assert f["edd_required"] is True


def test_business_owner_within_means_is_consistent():
    out = kyc_profile.run({"alert": {"customer_id": "CUST-20555", "total_amount": 20000}})
    f = out["kyc_findings"]
    assert f["income_mismatch"] is False
    assert f["edd_required"] is False


def test_missing_customer_is_handled():
    out = kyc_profile.run({"alert": {"customer_id": "CUST-DOES-NOT-EXIST", "total_amount": 5000}})
    assert out["kyc_findings"]["kyc_status"] == "Unknown"
