"""
4.x Data Quality Gate

Real compliance cases are not always clean -- customer records can be missing,
KYC can be incomplete, transaction history can be absent. Rather than push an
under-informed case through to a low-confidence SAR, this gate checks whether
the essential data exists.

If critical data is missing it returns status NEEDS_MORE_INFORMATION with the
list of missing fields, and the orchestrator halts the investigation and asks
for more information instead of producing an unreliable result.

Pure retrieval (DB lookups, no LLM).
"""

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.tools.db import get_customer, get_transactions


class DataQualityAgent(BaseAgent):
    name = "data_quality"
    label = "Data Quality Gate"

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cid = alert["customer_id"]
        cust = get_customer(cid)
        txns = get_transactions(cid)

        missing = []
        if not cust:
            missing += ["customer_profile", "customer_occupation",
                        "declared_income", "source_of_funds"]
        else:
            if not cust.get("occupation"):
                missing.append("customer_occupation")
            if not cust.get("declared_income"):
                missing.append("declared_income")
            if cust.get("kyc_status") != "Completed":
                missing.append("kyc_completion")
        if not txns:
            missing.append("transaction_history")
        if not alert.get("recipient"):
            missing.append("recipient_details")

        # critical gaps that make a reliable investigation impossible
        critical = (
            not cust
            or not txns
            or ("customer_occupation" in missing and "declared_income" in missing)
        )
        complete = not critical
        status = "complete" if complete else "needs_more_information"
        recommended = ("Sufficient data to proceed with the investigation."
                       if complete else
                       "Request additional customer information before SAR decision.")

        reasoning = (f"Data completeness check: "
                     f"{'all essential data present.' if complete else f'critical gaps - {missing}.'}")

        return {
            "data_quality": {
                "complete": complete,
                "status": status,
                "missing_fields": missing,
                "recommended_action": recommended,
            },
            "audit_rationales": [self.trace(reasoning, 0.95,
                                      output={"complete": complete, "missing": missing})],
            "audit": stamp(f"{self.label}: {status}"
                           + (f" (missing: {', '.join(missing)})" if missing else "")),
        }


data_quality = DataQualityAgent()
