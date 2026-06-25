"""
Case priority + SLA.

The intake agent assigns a provisional priority from the alert alone. Once the
investigation is done we know far more (risk score, sanctions match, typology,
triggered factors), so this module assigns the DEFINITIVE priority and the SLA
deadline an analyst must act by.

  P1 Critical : immediate review
  P2 High     : review within 4 hours
  P3 Medium   : review within 1 business day
  P4 Low      : monitor / batch review (no hard deadline)
"""

from datetime import datetime, timedelta, timezone

# SLA window (hours) and human label per priority. P4 has no hard deadline.
PRIORITY_SLA = {
    "P1": {"hours": 0,    "label": "Critical - immediate review"},
    "P2": {"hours": 4,    "label": "High - review within 4 hours"},
    "P3": {"hours": 24,   "label": "Medium - review within 1 business day"},
    "P4": {"hours": None, "label": "Low - monitor / batch review"},
}

# a confirmed hit on one of these lists is a P1 trigger
_SANCTION_LISTS = {"UN_SANCTIONS", "PEP", "INTERNAL_BLACKLIST"}


def assess_priority(state: dict) -> tuple[str, str]:
    """Return (priority, reason) from the post-investigation state."""
    score = state.get("risk_score", 0) or 0
    wf = state.get("watchlist_findings") or {}
    tf = state.get("transaction_findings") or {}
    fp = state.get("fp_review") or {}
    factors = state.get("risk_factors") or []
    typology = tf.get("typology")
    flags = tf.get("flags") or {}

    sanctions_match = bool(wf.get("is_match")) and wf.get("list_type") in _SANCTION_LISTS
    high_factors = [f for f in factors if f.get("severity") in ("CRITICAL", "HIGH")]
    high_risk_country = bool(wf.get("high_risk_country"))
    new_recipient = bool(flags.get("new_overseas_recipient")) or (tf.get("total_recent", 0) or 0) > 0
    money_mule = typology == "money mule"
    cleared_fp = fp and not fp.get("requires_human_review")

    # ---- P1 Critical ----
    if sanctions_match:
        return "P1", f"Confirmed watchlist match ({wf.get('list_type')}: {wf.get('best_match')})."
    if score >= 85:
        return "P1", f"Critical risk score ({score}/100)."
    if len(high_factors) >= 3:
        return "P1", f"Multiple high-risk factors ({len(high_factors)}): " \
                     f"{', '.join(f.get('name', '') for f in high_factors[:3])}."

    # ---- P2 High ----
    if 60 <= score <= 84:
        return "P2", f"High risk score ({score}/100)."
    if money_mule:
        return "P2", "Money-mule pattern detected (rapid inbound-then-onward transfers)."
    if high_risk_country and new_recipient:
        return "P2", "Transfer to a high-risk jurisdiction via a newly added recipient."

    # ---- P4 Low (strong false-positive clearance) ----
    if cleared_fp:
        return "P4", f"Low risk with a strong false-positive explanation: " \
                     f"{fp.get('clearance_reason') or 'documented benign activity'}."

    # ---- P3 Medium ----
    if 35 <= score <= 59:
        return "P3", f"Medium risk score ({score}/100)."
    if not wf.get("is_match"):
        return "P3", "Some concern but no watchlist match; purpose to be confirmed."

    # ---- P4 default ----
    return "P4", f"Low risk score ({score}/100); routine monitoring."


def sla_due_at(priority: str, start: str | None = None) -> str | None:
    """ISO timestamp by which the case must be reviewed, anchored to `start`
    (the case creation time, ISO string) or now. P4 has no hard deadline."""
    cfg = PRIORITY_SLA.get(priority, PRIORITY_SLA["P3"])
    hours = cfg["hours"]
    if hours is None:
        return None
    base = _parse(start) or datetime.now(timezone.utc)
    return (base + timedelta(hours=hours)).isoformat()


def sla_label(priority: str) -> str:
    return PRIORITY_SLA.get(priority, PRIORITY_SLA["P3"])["label"]


def _parse(iso: str | None):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None
