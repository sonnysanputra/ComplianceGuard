"""
4.3 KYC Profile Agent (multi-dimensional consistency)

Runs several profile-consistency checks rather than one:
  - income vs transaction volume
  - occupation vs activity (e.g. a student moving RM48k)
  - account age vs activity (brand-new account, high value)
  - elevated risk category
  - prior alert history

Qwen then judges overall consistency and whether Enhanced Due Diligence (EDD)
is warranted. Deterministic checks stay reliable; the LLM adds the judgment.
"""

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.core.evidence import EvidenceCollector
from app.tools.db import get_customer

# Occupations whose declared income rarely supports large transfers
LOW_INCOME_OCCUPATIONS = {"student", "unemployed", "junior clerk", "intern", "retiree"}

SYSTEM_PROMPT = """You are a KYC (Know Your Customer) analyst at a bank.

YOUR JOB
Judge whether the customer's declared profile is CONSISTENT with the flagged
activity, reasoning only from the facts and the failed deterministic checks given.

WHAT INCONSISTENCY LOOKS LIKE
- transaction volume far exceeding declared income
- occupation that cannot plausibly support the amounts (e.g. student, unemployed)
- a brand-new account already moving large sums
- an already-elevated risk category, or prior alert history

Enhanced Due Diligence (EDD) is warranted when the profile clearly cannot explain
the activity. Identify the single most significant concern.
"""


class KYCProfileAgent(BaseAgent):
    name = "kyc_profile"
    label = "KYC Profile Agent"

    def run(self, state: dict) -> dict:
        cid = state["alert"]["customer_id"]
        cust = get_customer(cid)
        burst = state["alert"].get("total_amount", 0)

        if not cust:
            return {
                "kyc_findings": {"declared_income": 0, "burst_total": burst,
                                 "income_mismatch": False, "kyc_status": "Unknown",
                                 "previous_alerts": 0, "checks_failed": [],
                                 "edd_required": False},
                "audit_rationales": [self.trace("Customer record not found.", 0.4)],
                "audit": stamp(f"{self.label} could not find customer {cid}"),
            }

        income = cust["declared_income"]
        occupation = (cust.get("occupation") or "").lower()
        age = cust.get("account_age_months", 0)
        income_ratio = round(burst / max(income, 1), 1)

        # --- multiple deterministic consistency checks ---
        checks = {
            "income_mismatch": burst > 2 * income,
            "occupation_risk": occupation in LOW_INCOME_OCCUPATIONS and burst > 10_000,
            "new_account_high_value": age < 6 and burst > 10_000,
            "elevated_risk_category": cust.get("risk_category") == "High",
            "prior_alerts": cust.get("previous_alerts", 0) > 0,
        }
        failed = [k for k, v in checks.items() if v]
        edd_required = len(failed) >= 2

        # --- Qwen judges overall consistency + EDD ---
        assessment = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                "CUSTOMER PROFILE\n"
                f"- occupation      : {cust.get('occupation')}\n"
                f"- declared_income : RM{income}/month\n"
                f"- account_age     : {age} months\n"
                f"- risk_category   : {cust.get('risk_category')}\n"
                f"- prior_alerts    : {cust.get('previous_alerts')}\n\n"
                f"FLAGGED ACTIVITY  : RM{burst} total ({income_ratio}x monthly income)\n"
                f"FAILED CHECKS     : {failed}\n\n"
                "Return ONLY this JSON:\n"
                "{\n"
                '  "consistency": "<consistent | partially_consistent | inconsistent>",\n'
                '  "key_concern": "<the single most significant inconsistency, or \'none\'>",\n'
                '  "edd_recommended": <true|false>,\n'
                '  "confidence": <0-100>,\n'
                '  "reasoning": "<2-3 sentences>"\n'
                "}\n\n"
                f"{CONFIDENCE_RUBRIC}"
            ),
        )
        reasoning = assessment.get("reasoning") or (
            f"{len(failed)} of {len(checks)} consistency checks failed.")
        confidence = float(assessment.get("confidence", 85)) / 100.0
        edd_required = edd_required or bool(assessment.get("edd_recommended"))
        consistency = assessment.get("consistency", "inconsistent" if failed else "consistent")
        key_concern = assessment.get("key_concern", failed[0] if failed else "none")

        # ---- structured evidence from the profile ----
        coll = EvidenceCollector()
        ev_ids = [coll.add("customer_profile", cid, "declared_income", income,
                           f"Declared income RM{income}/mo vs RM{burst} activity ({income_ratio}x)")]
        if cust.get("previous_alerts", 0):
            ev_ids.append(coll.add("customer_profile", cid, "previous_alerts",
                                   cust.get("previous_alerts", 0),
                                   f"{cust.get('previous_alerts')} prior alert(s) on record"))
        if checks["occupation_risk"]:
            ev_ids.append(coll.add("customer_profile", cid, "occupation",
                                   cust.get("occupation", ""),
                                   "Occupation unlikely to support the flagged amounts"))

        return {
            "kyc_findings": {
                "declared_income": income,
                "burst_total": burst,
                "income_ratio": income_ratio,
                "occupation": cust.get("occupation"),
                "account_age_months": age,
                "kyc_status": cust.get("kyc_status"),
                "previous_alerts": cust.get("previous_alerts", 0),
                "checks": checks,
                "checks_failed": failed,
                "consistency": consistency,
                "key_concern": key_concern,
                "income_mismatch": checks["income_mismatch"],   # kept for risk scoring
                "edd_required": edd_required,
                "evidence_ids": ev_ids,
            },
            "evidence": coll.items,
            "audit_rationales": [self.trace(
                reasoning, confidence,
                evidence=[f"{c.replace('_', ' ')} failed" for c in failed],
                output={"failed": failed, "edd": edd_required})],
            "audit": stamp(f"{self.label} ran {len(checks)} checks, {len(failed)} failed"
                           f"{' -> EDD' if edd_required else ''}"),
        }


kyc_profile = KYCProfileAgent()
