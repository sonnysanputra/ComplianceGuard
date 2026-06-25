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
from collections import defaultdict

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
# Transaction typology detection (driven by the declarative typology_rules)
# ======================================================================
_FLAG_TO_TYPOLOGY = {
    "money_mule": "money mule",
    "structuring": "structuring",
    "rapid_dispersion": "layering/dispersion",
    "new_overseas_recipient": "high-risk overseas transfer",
    "volume_spike": "volume spike",
}
# maps the internal flag name -> the YAML rule's `typology` field
_FLAG_TO_RULE = {
    "structuring": "structuring",
    "money_mule": "money_mule",
    "rapid_dispersion": "layering_dispersion",
    "new_overseas_recipient": "high_risk_overseas_transfer",
    "volume_spike": "volume_spike",
}


def _typology_rules() -> dict:
    return {r["typology"]: r for r in get_rules().get("typology_rules", [])}


def _classify(flags: dict) -> str:
    for flag, label in _FLAG_TO_TYPOLOGY.items():
        if flags.get(flag):
            return label
    return "none"


def _money(x) -> str:
    return f"{int(x):,}"


def _render(template: str, ctx: dict) -> str:
    """Render an evidence_template, tolerating missing placeholders."""
    if not template:
        return ""
    try:
        return template.format_map(defaultdict(lambda: "?", ctx))
    except Exception:
        return template


def detect_transaction_typology(transactions: list) -> dict:
    """Aggregate transaction facts and apply the SC red-flag typology rules
    (conditions come from typology_rules in aml_rules.yaml)."""
    rules = _typology_rules()
    crisk = get_country_risk()

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

    sc = rules["structuring"]["conditions"]
    mmc = rules["money_mule"]["conditions"]
    layc = rules["layering_dispersion"]["conditions"]
    geoc = rules["high_risk_overseas_transfer"]["conditions"]
    vsc = rules["volume_spike"]["conditions"]
    allowed_levels = set(geoc.get("recipient_country_risk_in", []))

    structuring_count = sum(
        1 for a in amounts
        if sc["amount_min_ratio_to_threshold"] * sc["internal_review_threshold"]
        <= a < sc["internal_review_threshold"])

    flags = {
        "structuring": structuring_count >= sc["min_transactions"] and window <= sc["window_hours"],
        "money_mule": (bool(incoming)
                       and incoming_total >= mmc["incoming_amount_min"]
                       and len(recent) >= mmc["min_new_recipients"]
                       and total_recent >= mmc["outgoing_ratio_min"] * max(incoming_total, 1)
                       and window <= mmc["max_forwarding_hours"]),
        "rapid_dispersion": (distinct >= layc["min_distinct_recipients"]
                             and window <= layc["window_hours"]),
        "new_overseas_recipient": any(crisk.get(c) in allowed_levels for c in countries),
        "volume_spike": total_recent > vsc["baseline_multiplier"] * max(avg_hist, 1),
    }
    return {
        "typology": _classify(flags), "flags": flags,
        "total_recent": total_recent, "distinct_recipients": distinct,
        "window_hours": round(window, 1), "amounts_recent": amounts,
        "structuring_count": structuring_count,
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
    rules = _typology_rules()
    wf = watchlist or {}
    mem = memory or {}
    det = detect_transaction_typology(transactions)
    flags = det["flags"]
    tr = det["total_recent"]
    fired: list[TriggeredRule] = []

    amounts = det["amounts_recent"]
    ctx = {
        "count": det["structuring_count"] or len(amounts),
        "min_amount": _money(min(amounts)) if amounts else "0",
        "max_amount": _money(max(amounts)) if amounts else "0",
        "window_hours": det["window_hours"],
        "incoming_total": _money(det["incoming_total"]),
        "total_recent": _money(tr),
        "distinct": det["distinct_recipients"],
        "avg_historical": _money(det["avg_historical"]),
        "countries": ", ".join(det["destination_countries"]),
    }

    # --- SC red-flag typology rules (metadata + evidence_template from YAML) ---
    for flag, typ in _FLAG_TO_RULE.items():
        if flags.get(flag) and typ in rules:
            r = rules[typ]
            fired.append(TriggeredRule(r["rule_id"], r["name"], r["risk_points"],
                                       r["severity"], _render(r.get("evidence_template"), ctx),
                                       source="SC Malaysia red-flag typology"))

    def fire(cfg, points, evidence):
        fired.append(TriggeredRule(cfg["rule_id"], cfg["name"], points, cfg["severity"], evidence))

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

    # --- false-positive reduction (negative adjustment) ---
    if mem.get("memory_risk_direction") == "reduce":
        fp = R["false_positive"]
        ev = _render(fp.get("evidence_template"),
                     {"prior_false_positives": mem.get("previous_false_positives", 0)})
        fired.append(TriggeredRule(fp["rule_id"], fp["name"], fp["risk_adjustment"],
                                   fp["severity"], ev, source="False positive check"))

    total = max(0, min(sum(r.points for r in fired), 100))
    return RuleResult(fired, total, det["typology"], flags)
