"""
AML Rule Engine -- the deterministic detection layer.

This is the single place that owns AML rule logic. It is PURE: it takes data
(customer, transactions, prior findings) as input and returns structured results
-- no database, no LLM, no I/O. Agents call it; they don't own the rules.

  detect_transaction_typology(transactions)            -> typology + flags + facts
  evaluate_aml_rules(customer, transactions, ...)      -> RuleResult (triggered
                                                          rules + score + typology)

Thresholds and risk points come from aml_rules.yaml; high-risk jurisdictions
from country_risk.yaml. Both are reloadable at runtime via reload_rules().
"""

import logging
from pathlib import Path
from datetime import datetime

import yaml

from app.rules.rule_models import TriggeredRule, RuleResult

logger = logging.getLogger(__name__)
_DIR = Path(__file__).parent

_rules = None
_countries = None


def _load(path: Path, default: dict) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or default
    except Exception as exc:
        logger.warning(f"[rules] could not load {path.name} ({exc}); using defaults")
        return default


def get_rules() -> dict:
    global _rules
    if _rules is None:
        _rules = _load(_DIR / "aml_rules.yaml", {})
    return _rules


def get_country_risk() -> dict:
    global _countries
    if _countries is None:
        _countries = _load(_DIR / "country_risk.yaml", {"countries": {}}).get("countries", {})
    return _countries


def high_risk_countries() -> set:
    return set(get_country_risk().keys())


def reload_rules() -> dict:
    """Re-read both YAML files at runtime (after editing thresholds/countries)."""
    global _rules, _countries
    _rules = None
    _countries = None
    get_country_risk()
    return get_rules()


# ======================================================================
# Transaction typology detection
# ======================================================================
def _classify(flags: dict) -> str:
    if flags["money_mule"]:             return "money mule"
    if flags["structuring"]:            return "structuring"
    if flags["rapid_dispersion"]:       return "layering/dispersion"
    if flags["new_overseas_recipient"]: return "high-risk overseas transfer"
    if flags["volume_spike"]:           return "volume spike"
    return "none"


def detect_transaction_typology(transactions: list) -> dict:
    """Aggregate transaction facts and apply the deterministic typology rules."""
    R = get_rules()
    s, mm = R["structuring"], R["money_mule"]
    lay, vs = R["layering_dispersion"], R["volume_spike"]
    hrc = high_risk_countries()

    outgoing = [t for t in transactions if t.get("direction", "out") == "out"]
    incoming = [t for t in transactions if t.get("direction") == "in"]
    recent = [t for t in outgoing if t["is_new_recipient"]]
    total_recent = sum(t["amount"] for t in recent)
    distinct = len({t["recipient"] for t in recent})
    times = sorted(datetime.fromisoformat(t["date_time"]) for t in recent)
    window = (times[-1] - times[0]).total_seconds() / 3600 if len(times) > 1 else 0
    historical = [t for t in outgoing if not t["is_new_recipient"]]
    avg_hist = sum(t["amount"] for t in historical) / len(historical) if historical else 0
    incoming_total = sum(t["amount"] for t in incoming)
    amounts = [t["amount"] for t in recent]
    countries = sorted({t["country"] for t in recent})

    flags = {
        "structuring": (
            sum(1 for a in amounts
                if s["lower_bound_ratio"] * s["internal_review_threshold"]
                <= a < s["internal_review_threshold"]) >= s["min_transactions"]
            and window <= s["window_hours"]),
        "money_mule": (bool(incoming)
                       and incoming_total >= mm["incoming_min_amount"]
                       and len(recent) >= mm["min_new_recipients"]
                       and total_recent >= mm["outgoing_ratio_min"] * max(incoming_total, 1)),
        "rapid_dispersion": (distinct >= lay["min_recipients"]
                             and window <= lay["window_hours"]),
        "new_overseas_recipient": any(c in hrc for c in countries),
        "volume_spike": total_recent > vs["baseline_multiplier"] * max(avg_hist, 1),
    }
    return {
        "typology": _classify(flags), "flags": flags,
        "total_recent": total_recent, "distinct_recipients": distinct,
        "window_hours": round(window, 1), "amounts_recent": amounts,
        "incoming_total": incoming_total, "avg_historical": round(avg_hist),
        "destination_countries": countries,
    }


# ======================================================================
# Full case evaluation -> triggered rules + total score + typology
# ======================================================================
def evaluate_aml_rules(customer: dict, transactions: list,
                       watchlist: dict = None, memory: dict = None,
                       alert: dict = None) -> RuleResult:
    """Run every AML rule over the case and return the triggered rules, the
    total rule score, and the detected typology. Pure -- no I/O."""
    R = get_rules()
    wf = watchlist or {}
    mem = memory or {}
    det = detect_transaction_typology(transactions)
    flags = det["flags"]
    tr, window, distinct = det["total_recent"], det["window_hours"], det["distinct_recipients"]
    fired: list[TriggeredRule] = []

    def fire(cfg, points, evidence):
        fired.append(TriggeredRule(cfg["rule_id"], cfg["name"], points, cfg["severity"], evidence))

    # --- transaction typology rules ---
    if flags["structuring"]:
        s = R["structuring"]
        n = sum(1 for a in det["amounts_recent"]
                if s["lower_bound_ratio"] * s["internal_review_threshold"]
                <= a < s["internal_review_threshold"])
        amt = det["amounts_recent"][0] if det["amounts_recent"] else 0
        fire(s, s["risk_points"],
             f"{n} transfers of ~RM{amt} (just under RM{s['internal_review_threshold']:,}) "
             f"within {window}h to a new recipient")
    if flags["money_mule"]:
        mm = R["money_mule"]
        fire(mm, mm["risk_points"],
             f"Inbound RM{det['incoming_total']} forwarded as RM{tr} to {distinct} new recipient(s)")
    if flags["rapid_dispersion"]:
        lay = R["layering_dispersion"]
        fire(lay, lay["risk_points"],
             f"Funds dispersed across {distinct} new recipients within {window}h")
    if flags["new_overseas_recipient"]:
        geo = R["high_risk_overseas"]
        fire(geo, geo["risk_points"],
             f"Transfer to high-risk jurisdiction(s): {', '.join(det['destination_countries'])}")
    if flags["volume_spike"]:
        vs = R["volume_spike"]
        fire(vs, vs["risk_points"],
             f"Burst of RM{tr} far exceeds the customer's baseline (avg RM{det['avg_historical']})")

    # --- KYC income / activity mismatch ---
    kyc = R["kyc"]
    income = (customer or {}).get("declared_income", 0) or 0
    burst = tr or (alert or {}).get("total_amount", 0)
    if income and burst > kyc["income_mismatch_ratio"] * income:
        fire(kyc, kyc["risk_points"],
             f"RM{burst} activity vs RM{income} declared monthly income "
             f"({round(burst / max(income, 1), 1)}x)")

    # --- watchlist ---
    wl = R["watchlist"]
    if wf.get("is_match"):
        fired.append(TriggeredRule(wl["match_rule_id"], wl["match_name"],
                                   wl["match_risk_points"], wl["match_severity"],
                                   f"Match: {wf.get('best_match')} "
                                   f"({wf.get('match_score')}%, {wf.get('list_type')})"))
    if wf.get("high_risk_country"):
        fired.append(TriggeredRule(wl["country_rule_id"], wl["country_name"],
                                   wl["high_risk_country_points"], wl["country_severity"],
                                   "Recipient jurisdiction is on the high-risk list"))

    # --- prior alert history ---
    hist = R["history"]
    prior = (customer or {}).get("previous_alerts", 0) or 0
    if prior > 0:
        fire(hist, hist["prior_alert_points"],
             f"{prior} prior alert(s) on the customer's KYC record")

    # --- long-term memory ---
    memcfg = R["memory"]
    if mem.get("previous_escalations", 0) > 0:
        fired.append(TriggeredRule(memcfg["escalation_rule_id"], memcfg["escalation_name"],
                                   memcfg["prior_escalation_points"], memcfg["escalation_severity"],
                                   f"{mem.get('previous_escalations')} prior escalation(s) for this customer"))
    if mem.get("same_recipient_seen_before"):
        fired.append(TriggeredRule(memcfg["recipient_rule_id"], memcfg["recipient_name"],
                                   memcfg["repeat_recipient_points"], memcfg["recipient_severity"],
                                   "Same recipient seen in a previous investigation"))

    # --- benign-history reduction (negative) ---
    if mem.get("memory_risk_direction") == "reduce":
        fp = R["false_positive"]
        fire(fp, -fp["risk_reduction_points"],
             f"{mem.get('previous_false_positives')} prior false positive(s), no escalations")

    total = max(0, min(sum(r.points for r in fired), 100))
    return RuleResult(fired, total, det["typology"], flags)
