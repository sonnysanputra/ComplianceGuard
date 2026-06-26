"""
4.x Data Quality Gate

Real compliance cases are not always clean -- customer records can be missing,
KYC can be incomplete, transaction history can be absent. Rather than push an
under-informed case through to a low-confidence SAR, this gate grades the data.

It returns a SEVERITY, not a binary flag:
  GOOD             : can proceed
  PARTIAL          : can proceed, but a human must review (degraded data)
  POOR             : stop and request more information
  CRITICAL_MISSING : stop immediately (essential records absent)

Pure retrieval (DB lookups, no LLM).
"""

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.tools.db import get_customer, get_transactions

# without these the investigation simply can't run -> stop immediately
_HARD_STOP = {"customer_profile", "transaction_history"}
_CRITICAL_PENALTY = 30
_OPTIONAL_PENALTY = 10
_GOOD_THRESHOLD = 85          # only-optional gaps below this -> PARTIAL


class DataQualityAgent(BaseAgent):
    name = "data_quality"
    label = "Data Quality Gate"
    uses_llm = False

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cust = get_customer(alert["customer_id"])
        txns = get_transactions(alert["customer_id"])

        missing_critical, missing_optional = [], []

        if not cust:
            missing_critical.append("customer_profile")
        else:
            occ, inc = cust.get("occupation"), cust.get("declared_income")
            if not occ and not inc:
                missing_critical.append("income_and_occupation")   # can't assess KYC fit
            else:
                if not occ:
                    missing_optional.append("customer_occupation")
                if not inc:
                    missing_optional.append("declared_income")
            if cust.get("kyc_status") != "Completed":
                missing_optional.append("kyc_completion")
        if not txns:
            missing_critical.append("transaction_history")
        if not alert.get("recipient"):
            missing_critical.append("recipient_details")
        if not alert.get("supporting_document"):
            missing_optional.append("supporting_invoice")

        # --- quality score (0-100) ---
        score = max(0, 100 - _CRITICAL_PENALTY * len(missing_critical)
                    - _OPTIONAL_PENALTY * len(missing_optional))

        # --- severity ---
        if set(missing_critical) & _HARD_STOP:
            severity = "CRITICAL_MISSING"
        elif missing_critical:
            severity = "POOR"
        elif missing_optional and score < _GOOD_THRESHOLD:
            severity = "PARTIAL"
        else:
            severity = "GOOD"

        can_continue = severity in ("GOOD", "PARTIAL")
        complete = severity == "GOOD"
        recommended = self._action(severity, missing_critical)

        reasoning = (f"Data quality {severity} (score {score}/100). "
                     + (f"Critical gaps: {missing_critical}. " if missing_critical else "")
                     + (f"Optional gaps: {missing_optional}." if missing_optional else "all key data present."))

        return {
            "data_quality": {
                "complete": complete,
                "can_continue": can_continue,
                "quality_score": score,
                "severity": severity,
                "missing_critical_fields": missing_critical,
                "missing_optional_fields": missing_optional,
                "missing_fields": missing_critical + missing_optional,   # back-compat
                "status": "complete" if can_continue else "needs_more_information",
                "recommended_action": recommended,
            },
            "audit_rationales": [self.trace(reasoning, 0.95,
                                      output={"severity": severity, "score": score,
                                              "missing_critical": missing_critical})],
            "audit": stamp(f"{self.label}: {severity} (score {score})"
                           + (f" — missing {', '.join(missing_critical + missing_optional)}"
                              if (missing_critical or missing_optional) else "")),
        }

    @staticmethod
    def _action(severity: str, missing_critical: list) -> str:
        if severity == "GOOD":
            return "Sufficient data to proceed with the investigation."
        if severity == "PARTIAL":
            return "Proceed, but require manual analyst review due to incomplete data."
        fields = ", ".join(missing_critical) or "the missing records"
        if severity == "POOR":
            return f"Request {fields} before risk scoring."
        return f"Halt immediately: essential records missing ({fields})."


data_quality = DataQualityAgent()
