"""
Case status lifecycle.

A case moves through a defined set of statuses, and only certain transitions are
allowed. Modelling this explicitly prevents impossible states (e.g. a case jumping
straight from intake to approved) and makes the workflow realistic and auditable --
every status change is checked against VALID_TRANSITIONS and recorded in
case_status_history.
"""


class CaseStatus:
    NEW = "NEW"
    INTAKE_COMPLETED = "INTAKE_COMPLETED"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"
    INVESTIGATION_RUNNING = "INVESTIGATION_RUNNING"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED"
    LOW_RISK_AUTO_CLEARED = "LOW_RISK_AUTO_CLEARED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    SAR_DRAFTED = "SAR_DRAFTED"
    AWAITING_ANALYST_REVIEW = "AWAITING_ANALYST_REVIEW"
    APPROVED_FOR_STR_REVIEW = "APPROVED_FOR_STR_REVIEW"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"
    ERROR_MANUAL_REVIEW = "ERROR_MANUAL_REVIEW"


ALL_STATUSES = [
    CaseStatus.NEW, CaseStatus.INTAKE_COMPLETED, CaseStatus.NEEDS_MORE_INFORMATION,
    CaseStatus.INVESTIGATION_RUNNING, CaseStatus.INVESTIGATION_COMPLETED,
    CaseStatus.LOW_RISK_AUTO_CLEARED, CaseStatus.MANUAL_REVIEW_REQUIRED,
    CaseStatus.SAR_DRAFTED, CaseStatus.AWAITING_ANALYST_REVIEW,
    CaseStatus.APPROVED_FOR_STR_REVIEW, CaseStatus.REJECTED, CaseStatus.CLOSED,
    CaseStatus.ERROR_MANUAL_REVIEW,
]

# statuses from which no further automatic transition is expected
TERMINAL_STATUSES = {
    CaseStatus.LOW_RISK_AUTO_CLEARED, CaseStatus.APPROVED_FOR_STR_REVIEW,
    CaseStatus.REJECTED, CaseStatus.CLOSED,
}

# the allowed forward transitions
VALID_TRANSITIONS = {
    CaseStatus.NEW: [CaseStatus.INTAKE_COMPLETED, CaseStatus.NEEDS_MORE_INFORMATION],
    CaseStatus.INTAKE_COMPLETED: [CaseStatus.INVESTIGATION_RUNNING],
    CaseStatus.NEEDS_MORE_INFORMATION: [CaseStatus.INVESTIGATION_RUNNING, CaseStatus.CLOSED],
    CaseStatus.INVESTIGATION_RUNNING: [CaseStatus.INVESTIGATION_COMPLETED,
                                       CaseStatus.ERROR_MANUAL_REVIEW],
    CaseStatus.INVESTIGATION_COMPLETED: [CaseStatus.LOW_RISK_AUTO_CLEARED,
                                         CaseStatus.SAR_DRAFTED,
                                         CaseStatus.MANUAL_REVIEW_REQUIRED],
    CaseStatus.MANUAL_REVIEW_REQUIRED: [CaseStatus.AWAITING_ANALYST_REVIEW],
    CaseStatus.SAR_DRAFTED: [CaseStatus.AWAITING_ANALYST_REVIEW],
    CaseStatus.AWAITING_ANALYST_REVIEW: [CaseStatus.APPROVED_FOR_STR_REVIEW,
                                         CaseStatus.REJECTED,
                                         CaseStatus.NEEDS_MORE_INFORMATION],
    CaseStatus.ERROR_MANUAL_REVIEW: [CaseStatus.AWAITING_ANALYST_REVIEW, CaseStatus.CLOSED],
    CaseStatus.APPROVED_FOR_STR_REVIEW: [CaseStatus.CLOSED],
    CaseStatus.REJECTED: [CaseStatus.CLOSED],
}


def is_valid_transition(old: str | None, new: str) -> bool:
    """True if `new` is a legal next status after `old`. A brand-new case
    (old is None) or a no-op (old == new) is always allowed."""
    if old is None or old == new:
        return True
    return new in VALID_TRANSITIONS.get(old, [])


# map the analyst's decision to the resulting lifecycle status
_DECISION_STATUS = {
    "approve": CaseStatus.APPROVED_FOR_STR_REVIEW,
    "edit": CaseStatus.APPROVED_FOR_STR_REVIEW,
    "reject": CaseStatus.REJECTED,
    "request_more_info": CaseStatus.NEEDS_MORE_INFORMATION,
}


def status_for_decision(decision: str) -> str:
    return _DECISION_STATUS.get(decision, CaseStatus.CLOSED)


def derive_status(values: dict, awaiting: bool) -> str:
    """Map the (possibly paused) graph state to the case's current lifecycle status.

    The graph runs to a terminal or paused point, so this returns the status the
    case has *reached* -- the intermediate running states are captured as the case
    is persisted over its lifetime (see case_status_history)."""
    dq = values.get("data_quality") or {}
    if dq and not dq.get("can_continue", dq.get("complete", True)):
        return CaseStatus.NEEDS_MORE_INFORMATION
    if values.get("errors") and not values.get("human_decision"):
        return CaseStatus.ERROR_MANUAL_REVIEW
    if values.get("human_decision"):
        return status_for_decision(values["human_decision"])
    if awaiting:
        return CaseStatus.AWAITING_ANALYST_REVIEW
    fp = values.get("fp_review") or {}
    if fp and not fp.get("requires_human_review"):
        return CaseStatus.LOW_RISK_AUTO_CLEARED
    if values.get("sar_draft"):
        return CaseStatus.SAR_DRAFTED
    return CaseStatus.LOW_RISK_AUTO_CLEARED
