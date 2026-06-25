"""
The case status lifecycle: valid transitions are enforced and the graph state
maps to the right lifecycle status.
"""

from app.core.case_status import (
    CaseStatus, ALL_STATUSES, VALID_TRANSITIONS,
    is_valid_transition, status_for_decision, derive_status,
)


def test_all_twelve_statuses_present():
    assert len(ALL_STATUSES) == 13   # 12 lifecycle + ERROR_MANUAL_REVIEW
    assert CaseStatus.AWAITING_ANALYST_REVIEW in ALL_STATUSES


def test_valid_and_invalid_transitions():
    assert is_valid_transition(CaseStatus.SAR_DRAFTED, CaseStatus.AWAITING_ANALYST_REVIEW)
    assert is_valid_transition(CaseStatus.AWAITING_ANALYST_REVIEW, CaseStatus.APPROVED_FOR_STR_REVIEW)
    # an impossible jump is rejected
    assert not is_valid_transition(CaseStatus.NEW, CaseStatus.APPROVED_FOR_STR_REVIEW)
    assert not is_valid_transition(CaseStatus.INTAKE_COMPLETED, CaseStatus.REJECTED)
    # a brand-new case (no prior status) or a no-op is always allowed
    assert is_valid_transition(None, CaseStatus.INTAKE_COMPLETED)
    assert is_valid_transition(CaseStatus.CLOSED, CaseStatus.CLOSED)


def test_transition_targets_are_known_statuses():
    for src, targets in VALID_TRANSITIONS.items():
        assert src in ALL_STATUSES
        for t in targets:
            assert t in ALL_STATUSES


def test_decision_maps_to_status():
    assert status_for_decision("approve") == CaseStatus.APPROVED_FOR_STR_REVIEW
    assert status_for_decision("reject") == CaseStatus.REJECTED
    assert status_for_decision("request_more_info") == CaseStatus.NEEDS_MORE_INFORMATION


def test_derive_status_from_graph_state():
    # incomplete data
    assert derive_status({"data_quality": {"complete": False}}, False) == CaseStatus.NEEDS_MORE_INFORMATION
    # tool failure
    assert derive_status({"errors": [{"agent": "x"}]}, False) == CaseStatus.ERROR_MANUAL_REVIEW
    # paused for the analyst
    assert derive_status({"sar_draft": "..."}, True) == CaseStatus.AWAITING_ANALYST_REVIEW
    # cleared false positive
    assert derive_status({"fp_review": {"requires_human_review": False}}, False) == CaseStatus.LOW_RISK_AUTO_CLEARED
    # analyst approved
    assert derive_status({"human_decision": "approve"}, False) == CaseStatus.APPROVED_FOR_STR_REVIEW
    # clean low-risk close
    assert derive_status({}, False) == CaseStatus.LOW_RISK_AUTO_CLEARED
