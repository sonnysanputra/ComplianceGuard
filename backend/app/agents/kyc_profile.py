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

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.tools.db import get_customer

# Occupations whose declared income rarely supports large transfers
LOW_INCOME_OCCUPATIONS = {"student", "unemployed", "junior clerk", "intern", "retiree"}


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
                "cot_traces": [self.trace("Customer record not found.", 0.4)],
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
            system=("You are a KYC analyst. Judge whether the customer's profile is "
                    "consistent with the flagged activity, using only the facts given."),
            prompt=(f"Profile: occupation={cust.get('occupation')}, "
                    f"declared_income=RM{income}/mo, account_age={age}mo, "
                    f"risk_category={cust.get('risk_category')}, "
                    f"prior_alerts={cust.get('previous_alerts')}.\n"
                    f"Flagged activity total: RM{burst} (={income_ratio}x monthly income).\n"
                    f"Failed consistency checks: {failed}.\n"
                    'Return JSON: {"consistent": true/false, "edd_recommended": true/false, '
                    '"confidence": <0-100>, "reasoning": "<2-3 sentences>"}'),
        )
        reasoning = assessment.get("reasoning") or (
            f"{len(failed)} of {len(checks)} consistency checks failed.")
        confidence = float(assessment.get("confidence", 85)) / 100.0
        edd_required = edd_required or bool(assessment.get("edd_recommended"))

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
                "income_mismatch": checks["income_mismatch"],   # kept for risk scoring
                "edd_required": edd_required,
            },
            "cot_traces": [self.trace(reasoning, confidence,
                                      output={"failed": failed, "edd": edd_required})],
            "audit": stamp(f"{self.label} ran {len(checks)} checks, {len(failed)} failed"
                           f"{' -> EDD' if edd_required else ''}"),
        }


kyc_profile = KYCProfileAgent()
