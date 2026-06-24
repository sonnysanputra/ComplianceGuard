from .base import BaseAgent
from ..state import stamp


class AlertIntakeAgent(BaseAgent):
    name = "alert_intake"
    label = "Alert Intake Agent"

    def run(self, state: dict) -> dict:
        alert = state["alert"]

        summary = (f"Alert {alert['id']} for {alert['customer_id']}: "
                   f"{alert['reason']}")

        # Deterministic confidence: how many key fields the alert actually has.
        required = ["id", "customer_id", "reason", "recipient", "total_amount"]
        present = [f for f in required if alert.get(f) not in (None, "", 0)]
        confidence = len(present) / len(required)

        reasoning = (
            f"Parsed alert {alert['id']}. {len(present)}/{len(required)} key "
            f"fields present. Classified trigger: '{alert.get('reason')}'. "
            f"Next steps: transaction, KYC, watchlist, and policy checks."
        )

        return {
            "case_summary": summary,
            "cot_traces": [self.trace(reasoning, confidence)],
            "audit": stamp(f"{self.label} processed {alert['id']}"),
        }


# Instance used as the LangGraph node
alert_intake = AlertIntakeAgent()
