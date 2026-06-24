"""
4.2 Transaction Analysis Agent

Pulls transaction history (tool call) and detects multiple AML typologies with
pure-Python math, then uses ONE LLM call to summarize the pattern + self-rate
confidence.

Typologies detected:
  - structuring        : repeated transfers just under the reporting threshold
  - money mule         : large inbound funds rapidly forwarded out
  - layering/dispersion: funds split across many new recipients quickly
  - new overseas       : transfers to high-risk jurisdictions
  - volume spike       : activity far above the customer's own baseline
"""

from datetime import datetime

from .base import BaseAgent
from ..state import stamp
from ..tools.db import get_transactions, HIGH_RISK_COUNTRIES

REPORTING_THRESHOLD = 10_000   # RM -- amounts just under this suggest structuring


class TransactionAnalysisAgent(BaseAgent):
    name = "transaction_analysis"
    label = "Transaction Analysis Agent"

    def run(self, state: dict) -> dict:
        cid = state["alert"]["customer_id"]
        txns = get_transactions(cid)                       # tool call, no cost

        outgoing = [t for t in txns if t.get("direction", "out") == "out"]
        incoming = [t for t in txns if t.get("direction") == "in"]

        # "recent" = the suspicious burst (transfers to newly added recipients)
        recent = [t for t in outgoing if t["is_new_recipient"]]
        total_recent = sum(t["amount"] for t in recent)
        distinct_recipients = len({t["recipient"] for t in recent})
        times = sorted(datetime.fromisoformat(t["date_time"]) for t in recent)
        window_hours = (times[-1] - times[0]).total_seconds() / 3600 if len(times) > 1 else 0

        # baseline = the customer's own normal behaviour
        historical = [t for t in outgoing if not t["is_new_recipient"]]
        avg_historical = (sum(t["amount"] for t in historical) / len(historical)
                          if historical else 0)
        incoming_total = sum(t["amount"] for t in incoming)

        # --- typology flags (deterministic, auditable) ---
        flags = {
            "structuring": sum(
                1 for t in recent if 0.9 * REPORTING_THRESHOLD <= t["amount"] < REPORTING_THRESHOLD
            ) >= 3,
            "money_mule": bool(incoming) and len(recent) >= 2
                          and total_recent >= 0.6 * max(incoming_total, 1),
            "rapid_dispersion": distinct_recipients >= 5 and window_hours <= 48,
            "new_overseas_recipient": any(t["country"] in HIGH_RISK_COUNTRIES for t in recent),
            "volume_spike": total_recent > 10 * max(avg_historical, 1),
        }
        typology = self._classify(flags)

        # --- one LLM call: reasoning + confidence (cost-aware) ---
        reasoning, confidence = self.reason(
            system="You are an AML transaction analyst. Be concise and factual.",
            prompt=(f"Detected typology: {typology}. {len(recent)} transfers "
                    f"totalling RM{total_recent} across {distinct_recipients} new "
                    f"recipient(s) within {window_hours:.0f}h; inbound RM{incoming_total}; "
                    f"customer's usual transaction averages RM{avg_historical:.0f}. "
                    f"Summarize the suspicious pattern in 2 sentences."),
        )

        return {
            "transaction_findings": {
                "flags": flags, "typology": typology,
                "total_recent": total_recent,
                "distinct_recipients": distinct_recipients,
                "window_hours": round(window_hours, 1), "summary": reasoning,
            },
            "cot_traces": [self.trace(reasoning, confidence, output={"typology": typology})],
            "audit": stamp(f"{self.label} detected typology: {typology}"),
        }

    @staticmethod
    def _classify(flags: dict) -> str:
        """Pick the dominant typology label for the case."""
        if flags["money_mule"]:
            return "Money mule (rapid pass-through)"
        if flags["structuring"]:
            return "Structuring (sub-threshold transfers)"
        if flags["rapid_dispersion"]:
            return "Layering / dispersion"
        if flags["new_overseas_recipient"]:
            return "High-risk overseas transfer"
        if flags["volume_spike"]:
            return "Volume spike"
        return "No clear suspicious pattern"


transaction_analysis = TransactionAnalysisAgent()
