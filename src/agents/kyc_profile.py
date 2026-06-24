"""
4.3 KYC Profile Agent

Fetches the customer's KYC record (tool call) and compares declared income to
the transaction burst. Pure Python -- confidence reflects data completeness.
"""

from .base import BaseAgent
from ..state import stamp
from ..tools.db import get_customer


class KYCProfileAgent(BaseAgent):
    name = "kyc_profile"
    label = "KYC Profile Agent"

    def run(self, state: dict) -> dict:
        cid = state["alert"]["customer_id"]
        cust = get_customer(cid)                           # tool call, no cost
        burst_total = state["alert"].get("total_amount", 0)
        income = cust["declared_income"] if cust else 0

        mismatch = burst_total > 2 * income                # simple, explainable rule

        reasoning = (
            f"Declared income RM{income}/month vs burst transfers RM{burst_total}. "
            f"{'Income inconsistent with activity.' if mismatch else 'Within plausible range.'} "
            f"KYC status: {cust['kyc_status'] if cust else 'Unknown'}."
        )
        # confident when we actually found the customer record
        confidence = 0.9 if cust else 0.4

        return {
            "kyc_findings": {
                "declared_income": income,
                "burst_total": burst_total,
                "income_mismatch": mismatch,
                "kyc_status": cust["kyc_status"] if cust else "Unknown",
                "previous_alerts": cust["previous_alerts"] if cust else 0,
            },
            "cot_traces": [self.trace(reasoning, confidence, output={"income_mismatch": mismatch})],
            "audit": stamp(f"{self.label} checked income-to-transaction consistency"),
        }


kyc_profile = KYCProfileAgent()
