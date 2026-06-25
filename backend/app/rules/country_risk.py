"""
Country-risk register module.

Loads the structured country-risk register (country_risk.yaml) and exposes a
clean API over it. Each country carries a risk_level, a reason, a source, and a
last_reviewed date -- so a high-risk flag is always explainable and attributable.

In production this register would be sourced from FATF public statements, UN
sanctions lists, regulator guidance, and the institution's own country-risk
assessment. Here it is a demo register (e.g. Cambodia is an INTERNAL demo
high-risk setting, not an official FATF listing).
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
_PATH = Path(__file__).parent / "country_risk.yaml"

# levels treated as high-risk for screening/escalation
HIGH_RISK_LEVELS = {"HIGH", "CALL_FOR_ACTION", "INCREASED_MONITORING"}

_register = None


def get_country_risk() -> dict:
    """The full register: {country: {risk_level, reason, source, last_reviewed}}."""
    global _register
    if _register is None:
        try:
            _register = (yaml.safe_load(_PATH.read_text(encoding="utf-8"))
                         or {}).get("countries", {})
        except Exception as exc:
            logger.warning(f"[country_risk] could not load register ({exc}); empty")
            _register = {}
    return _register


def reload_country_risk() -> dict:
    global _register
    _register = None
    return get_country_risk()


def risk_info(country: str) -> dict | None:
    return get_country_risk().get(country)


def risk_level(country: str) -> str | None:
    info = risk_info(country)
    return info.get("risk_level") if info else None


def is_high_risk(country: str) -> bool:
    return risk_level(country) in HIGH_RISK_LEVELS


def high_risk_countries() -> set:
    """The set of countries currently designated high-risk."""
    return {c for c, info in get_country_risk().items()
            if info.get("risk_level") in HIGH_RISK_LEVELS}


def describe(country: str) -> str:
    """Human-readable one-liner for evidence, e.g. 'Cambodia (HIGH, Internal demo)'."""
    info = risk_info(country)
    if not info:
        return country
    return f"{country} ({info.get('risk_level')}, {info.get('source')})"
