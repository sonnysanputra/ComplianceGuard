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
from app.core.baseline import behavior_deviations
# country risk lives in its own structured register module
from app.rules.country_risk import (
    get_country_risk, high_risk_countries, risk_level, describe,
    reload_country_risk,
)

logger = logging.getLogger(__name__)
_DIR = Path(__file__).parent

_rules = None


def get_rules() -> dict:
    global _rules
    if _rules is None:
        try:
            _rules = yaml.safe_load((_DIR / "aml_rules.yaml").read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning(f"[rules] could not load aml_rules.yaml ({exc})")
            _rules = {}
    return _rules


def reload_rules() -> dict:
    """Re-read the rule YAML + the country-risk register at runtime."""
    global _rules
    _rules = None
    reload_country_risk()
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


# values that mean "no real economic purpose was stated"
_VAGUE_PURPOSES = {"", "unknown", "unspecified", "n/a", "na", "none",
                   "other", "unclear", "personal", "misc", "-"}


def purpose_is_clear(purpose) -> bool:
    """True if a transaction carries a meaningful stated economic purpose."""
    return bool(purpose) and str(purpose).strip().lower() not in _VAGUE_PURPOSES


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
        "new_overseas_recipient": any(risk_level(c) in allowed_levels for c in countries),
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
                       alert: dict = None, adverse_media: dict = None,
                       graph: dict = None) -> RuleResult:
    """Run every AML rule over the case and return the triggered rules, the
    total rule score, and the detected typology. Pure -- no I/O."""
    R = get_rules()
    rules = _typology_rules()
    wf = watchlist or {}
    mem = memory or {}
    am = adverse_media or {}
    gf = graph or {}
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
        "countries": ", ".join(describe(c) for c in det["destination_countries"]),
    }

    # ---- structured evidence inputs per typology (resolved to IDs by risk scoring) ----
    def ev(source_type, source_id, fieldname, value, description):
        return {"source_type": source_type, "source_id": str(source_id),
                "field": fieldname, "value": value, "description": description}

    cid = (customer or {}).get("customer_id", "unknown")
    outgoing = [t for t in transactions if t.get("direction", "out") == "out"]
    incoming = [t for t in transactions if t.get("direction") == "in"]
    recent = [t for t in outgoing if t.get("is_new_recipient")]
    sc_c = rules.get("structuring", {}).get("conditions", {})
    thr = sc_c.get("internal_review_threshold", 10000)
    near_lo = sc_c.get("amount_min_ratio_to_threshold", 0.9) * thr
    geo_levels = set(rules.get("high_risk_overseas_transfer", {})
                     .get("conditions", {}).get("recipient_country_risk_in", []))

    typ_evidence = {
        "structuring": [ev("transaction", t.get("transaction_id"), "amount", t["amount"],
                           "Transfer close to the internal review threshold")
                        for t in recent if near_lo <= t["amount"] < thr],
        "money_mule": [ev("transaction", t.get("transaction_id"), "amount", t["amount"],
                          "Large incoming funds") for t in incoming]
                      + [ev("transaction", t.get("transaction_id"), "recipient", t["recipient"],
                            "Rapid onward transfer to a new recipient") for t in recent],
        "layering_dispersion": [ev("transaction", t.get("transaction_id"), "recipient", t["recipient"],
                                   "Funds dispersed to a newly added recipient") for t in recent],
        "high_risk_overseas_transfer": [
            ev("transaction", t.get("transaction_id"), "country", t["country"],
               "Transfer to a flagged jurisdiction")
            for t in recent if t.get("country") and risk_level(t["country"]) in geo_levels],
        "volume_spike": [ev("transaction", t.get("transaction_id"), "amount", t["amount"],
                            "Activity above the customer's historical baseline") for t in recent],
    }

    # --- SC red-flag typology rules (metadata + evidence_template from YAML) ---
    for flag, typ in _FLAG_TO_RULE.items():
        if flags.get(flag) and typ in rules:
            r = rules[typ]
            fired.append(TriggeredRule(r["rule_id"], r["name"], r["risk_points"],
                                       r["severity"], _render(r.get("evidence_template"), ctx),
                                       source="SC Malaysia red-flag typology",
                                       evidence_items=typ_evidence.get(typ, [])))

    def fire(cfg, points, evidence, items=None):
        fired.append(TriggeredRule(cfg["rule_id"], cfg["name"], points, cfg["severity"],
                                   evidence, evidence_items=items or []))

    # --- unclear economic purpose on a high-risk overseas transfer ---
    up = R.get("unclear_purpose")
    if up:
        overseas_unclear = [
            t for t in recent
            if t.get("country") and risk_level(t["country"]) in geo_levels
            and not purpose_is_clear(t.get("transaction_purpose"))]
        if overseas_unclear:
            fire(up, up["risk_points"],
                 f"{len(overseas_unclear)} transfer(s) to a high-risk jurisdiction with "
                 f"no clear economic purpose stated",
                 items=[ev("transaction", t.get("transaction_id"), "transaction_purpose",
                           t.get("transaction_purpose") or "(none)",
                           "No stated economic purpose for a high-risk overseas transfer")
                        for t in overseas_unclear])

    # --- KYC income / activity mismatch ---
    kyc = R["kyc"]
    income = (customer or {}).get("declared_income", 0) or 0
    burst = tr or (alert or {}).get("total_amount", 0)
    if income and burst > kyc["income_mismatch_ratio"] * income:
        fire(kyc, kyc["risk_points"],
             f"RM{burst} activity vs RM{income} declared monthly income "
             f"({round(burst / max(income, 1), 1)}x)",
             items=[ev("customer_profile", cid, "declared_income", income,
                       f"Declared income RM{income}/mo vs RM{burst} flagged activity")])

    # --- watchlist ---
    wl = R["watchlist"]
    if wf.get("is_match"):
        fired.append(TriggeredRule(wl["match_rule_id"], wl["match_name"],
                                   wl["match_risk_points"], wl["match_severity"],
                                   f"Match: {wf.get('best_match')} "
                                   f"({wf.get('match_score')}%, {wf.get('list_type')})",
                                   evidence_items=[ev("watchlist", wf.get("best_match"),
                                       "match_score", wf.get("match_score"),
                                       f"{wf.get('list_type')} name match")]))
    if wf.get("high_risk_country"):
        fired.append(TriggeredRule(wl["country_rule_id"], wl["country_name"],
                                   wl["high_risk_country_points"], wl["country_severity"],
                                   "Recipient jurisdiction is on the high-risk list",
                                   evidence_items=[ev("transaction", (alert or {}).get("recipient", "recipient"),
                                       "country", (alert or {}).get("country", ""),
                                       "Recipient jurisdiction is on the high-risk list")]))

    # --- adverse media / negative news ---
    amcfg = R.get("adverse_media")
    if amcfg and am.get("negative_news"):
        critical = am.get("highest_risk_level") == "CRITICAL"
        points = amcfg.get("critical_risk_points", amcfg["risk_points"]) if critical \
            else amcfg["risk_points"]
        hits = am.get("all_hits", [])
        titles = "; ".join(h.get("title", "") for h in hits[:2])
        fired.append(TriggeredRule(
            amcfg["rule_id"], amcfg["name"], points, amcfg["severity"],
            f"{am.get('hit_count', len(hits))} negative-news hit(s) "
            f"(highest {am.get('highest_risk_level')}): {titles}",
            source="Adverse media screening",
            evidence_items=[ev("adverse_media", h.get("name"), "negative_news",
                               h.get("risk_level"), h.get("title")) for h in hits]))

    # --- relationship-graph network risk (layering / mule) ---
    gcfg = R.get("graph_network")
    if gcfg and gf.get("graph_risk_score", 0) > 0:
        pts = min(gf["graph_risk_score"], gcfg.get("max_points", 30))
        path = gf.get("possible_layering_path") or []
        bits = []
        if gf.get("fan_out_count", 0) >= 5:
            bits.append(f"fan-out to {gf['fan_out_count']} accounts")
        if gf.get("rapid_forwarding_detected"):
            bits.append("rapid forwarding")
        if gf.get("common_recipient"):
            bits.append(f"convergence on {', '.join(gf['common_recipient'][:2])}")
        if gf.get("circular_flow"):
            bits.append("circular flow")
        fire(gcfg, pts,
             "Money-flow network: " + ("; ".join(bits) or "elevated network risk")
             + (f"; path {' -> '.join(path)}" if len(path) >= 3 else ""),
             items=[ev("transaction", (customer or {}).get("customer_id", "account"),
                       "graph_risk_score", gf["graph_risk_score"],
                       "Relationship-graph network laundering signature")])

    # --- account behaviour baseline deviations ---
    bcfg = R.get("behavior_baseline")
    if bcfg:
        for d in behavior_deviations(transactions, alert or {}, bcfg):
            fired.append(TriggeredRule(d["rule_id"], d["name"], d["points"], d["severity"],
                                       d["evidence"], source="Account behaviour baseline",
                                       evidence_items=d.get("evidence_items", [])))

    # --- prior alert history ---
    hist = R["history"]
    prior = (customer or {}).get("previous_alerts", 0) or 0
    if prior > 0:
        fire(hist, hist["prior_alert_points"],
             f"{prior} prior alert(s) on the customer's KYC record",
             items=[ev("customer_profile", cid, "previous_alerts", prior,
                       f"{prior} prior alert(s) on record")])

    # --- long-term memory ---
    memcfg = R["memory"]
    if mem.get("previous_escalations", 0) > 0:
        fired.append(TriggeredRule(memcfg["escalation_rule_id"], memcfg["escalation_name"],
                                   memcfg["prior_escalation_points"], memcfg["escalation_severity"],
                                   f"{mem.get('previous_escalations')} prior escalation(s) for this customer",
                                   evidence_items=[ev("memory", cid, "previous_escalations",
                                       mem.get("previous_escalations"),
                                       "Prior escalation(s) for this customer")]))
    if mem.get("same_recipient_seen_before"):
        fired.append(TriggeredRule(memcfg["recipient_rule_id"], memcfg["recipient_name"],
                                   memcfg["repeat_recipient_points"], memcfg["recipient_severity"],
                                   "Same recipient seen in a previous investigation",
                                   evidence_items=[ev("memory", cid, "same_recipient_seen_before", True,
                                       "Same recipient seen in a previous investigation")]))

    # --- false-positive reduction (negative adjustment) ---
    if mem.get("memory_risk_direction") == "reduce":
        fp = R["false_positive"]
        fp_ev = _render(fp.get("evidence_template"),
                        {"prior_false_positives": mem.get("previous_false_positives", 0)})
        fired.append(TriggeredRule(fp["rule_id"], fp["name"], fp["risk_adjustment"],
                                   fp["severity"], fp_ev, source="False positive check",
                                   evidence_items=[ev("memory", cid, "previous_false_positives",
                                       mem.get("previous_false_positives", 0),
                                       "Prior false positive(s) for this customer")]))

    total = max(0, min(sum(r.points for r in fired), 100))
    return RuleResult(fired, total, det["typology"], flags)
