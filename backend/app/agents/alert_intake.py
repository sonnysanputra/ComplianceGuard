"""
4.1 Alert Intake & Triage Agent

First-pass triage of an incoming alert:
  - classifies the alert type from the trigger reason
  - assigns a severity (from amount) and a case priority P1-P4
  - extracts the key entities (parties, amount, jurisdiction)
  - decides which investigations to trigger (routing)
  - confirms the triage with a short Qwen assessment (reasoning + confidence)

Deterministic classification keeps triage fast and reliable; Qwen adds the
human-readable justification and a confidence score.
"""

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.rules.rule_engine import high_risk_countries

SYSTEM_PROMPT = """You are an AML intake officer triaging an incoming suspicious-activity \
alert before investigation.

YOUR JOB
Confirm the triage (alert type, severity, priority) and justify the priority briefly,
using ONLY the facts provided. Do not invent details. Priorities mean:
- P1: act now (very large amount, or transfer to a high-risk jurisdiction)
- P2: high (large amount)
- P3: medium  - P4: routine
"""


class AlertIntakeAgent(BaseAgent):
    name = "alert_intake"
    label = "Alert Intake Agent"

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        amount = alert.get("total_amount", 0)
        recipient_country = alert.get("country", "")
        reason = (alert.get("reason") or "").lower()

        alert_type = self._classify_type(reason)
        severity = ("High" if amount >= 25_000 else
                    "Medium" if amount >= 10_000 else "Low")

        # priority: P1 (act now) .. P4 (routine)
        overseas = recipient_country in high_risk_countries()
        if amount >= 25_000 or overseas:
            priority = "P1"
        elif amount >= 10_000:
            priority = "P2"
        elif amount >= 5_000:
            priority = "P3"
        else:
            priority = "P4"

        entities = {
            "customer_id": alert.get("customer_id"),
            "recipient": alert.get("recipient"),
            "amount": amount,
            "jurisdiction": recipient_country,
            "num_transactions": alert.get("num_transactions"),
        }
        investigations = ["transaction_analysis", "kyc_profile",
                          "watchlist_screening", "policy_rag"]

        required = ["id", "customer_id", "reason", "recipient", "total_amount"]
        completeness = sum(1 for f in required if alert.get(f) not in (None, "", 0)) / len(required)

        # short Qwen triage confirmation (reasoning + confidence)
        assessment = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                "ALERT TRIAGE\n"
                f"- type             : {alert_type}\n"
                f"- severity         : {severity}\n"
                f"- priority         : {priority}\n"
                f"- amount           : RM{amount}\n"
                f"- jurisdiction     : {recipient_country}\n"
                f"- overseas_high_risk: {overseas}\n\n"
                "Return ONLY this JSON:\n"
                '{ "confidence": <0-100>, "reasoning": "<1-2 sentence priority justification>" }\n\n'
                f"{CONFIDENCE_RUBRIC}"
            ),
        )
        reasoning = assessment.get("reasoning") or (
            f"Classified as {alert_type}; severity {severity}; priority {priority}.")
        confidence = float(assessment.get("confidence", completeness * 100)) / 100.0

        summary = (f"Alert {alert['id']} ({alert_type}, {severity} severity, {priority}) "
                   f"for {alert['customer_id']}.")

        return {
            "case_summary": summary,
            "triage": {
                "alert_type": alert_type,
                "severity": severity,
                "priority": priority,
                "entities": entities,
                "triggered_investigations": investigations,
                "field_completeness": round(completeness, 2),
            },
            "audit_rationales": [self.trace(reasoning, confidence,
                                      output={"type": alert_type, "priority": priority})],
            "audit": stamp(f"{self.label} triaged {alert['id']} -> {alert_type} ({priority})"),
        }

    @staticmethod
    def _classify_type(reason: str) -> str:
        # real structuring = sub-threshold AND repeated; a lone threshold trip is not
        structuring = "structuring" in reason or (
            "threshold" in reason
            and any(w in reason for w in ("multiple", "under", "below")))
        if structuring:
            return "Structuring"
        if "forwarded" in reason or "incoming" in reason or "mule" in reason:
            return "Money mule"
        if "dispersed" in reason or "many" in reason or "dispersion" in reason:
            return "Layering / dispersion"
        if "overseas" in reason or "foreign" in reason:
            return "Overseas transfer"
        if "threshold" in reason:
            return "Threshold-triggered alert"
        return "General suspicious activity"


alert_intake = AlertIntakeAgent()
