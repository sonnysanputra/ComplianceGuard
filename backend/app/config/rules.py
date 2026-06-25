"""
AML rule configuration loader.

Rules (typology thresholds, risk points, the escalation threshold) live in
risk_rules.yaml so they can be tuned per institution WITHOUT touching code --
exactly how a real AML engine externalises its rule set. Falls back to safe
built-in defaults if the file is missing or unreadable.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).parent / "risk_rules.yaml"

# Built-in fallback so the system runs even without the YAML file.
_DEFAULTS = {
    "currency": "MYR",
    "structuring": {"internal_review_threshold": 10000, "lower_bound_ratio": 0.90,
                    "min_transactions": 3, "window_hours": 24, "risk_points": 25},
    "money_mule": {"incoming_min_amount": 20000, "outgoing_ratio_min": 0.80,
                   "max_forwarding_hours": 24, "min_new_recipients": 2, "risk_points": 30},
    "layering_dispersion": {"min_recipients": 5, "window_hours": 24, "risk_points": 30},
    "high_risk_overseas": {"new_recipient_required": True, "risk_points": 20},
    "volume_spike": {"baseline_multiplier": 10, "risk_points": 15},
    "kyc": {"income_mismatch_ratio": 2.0, "risk_points": 20},
    "watchlist": {"match_threshold": 80, "review_threshold": 70,
                  "match_risk_points": 25, "high_risk_country_points": 10},
    "history": {"prior_alert_points": 10},
    "memory": {"prior_escalation_points": 15, "repeat_recipient_points": 10},
    "false_positive": {"known_recipient_required": True,
                       "supporting_document_required": True, "risk_reduction_points": 35},
    "scoring": {"escalation_threshold": 60},
}

_rules = None


def get_rules() -> dict:
    """Return the loaded rule set (cached)."""
    global _rules
    if _rules is None:
        try:
            _rules = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or _DEFAULTS
        except Exception as exc:
            logger.warning(f"[rules] could not load risk_rules.yaml ({exc}); using defaults")
            _rules = _DEFAULTS
    return _rules


def reload_rules() -> dict:
    """Re-read risk_rules.yaml at runtime (after editing thresholds)."""
    global _rules
    _rules = None
    return get_rules()
