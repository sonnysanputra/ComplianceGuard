"""
4.7 SAR Drafting Agent

Generates the Suspicious Activity Report draft for human review. This is the one
node where the LLM genuinely earns its keep (real writing), so it uses self.llm.
"""

from .base import BaseAgent
from ..state import stamp


class SARDraftingAgent(BaseAgent):
    name = "sar_drafting"
    label = "SAR Drafting Agent"

    def run(self, state: dict) -> dict:
        draft = self.llm(
            system="You write formal Suspicious Activity Report (SAR) drafts for human review.",
            prompt=(
                "Write a concise SAR draft with these sections: Customer Information, "
                "Alert Summary, Suspicious Indicators, Risk Assessment, Recommended Action.\n\n"
                f"Alert: {state['alert']}\n"
                f"Transaction summary: {state['transaction_findings']['summary']}\n"
                f"KYC findings: {state['kyc_findings']}\n"
                f"Watchlist: {state['watchlist_findings']}\n"
                f"Risk: {state['risk_score']}/100 - {state['risk_explanation']}\n"
                f"Policy basis: {state.get('retrieved_policies')}"
            ),
        )

        reasoning = "Drafted a structured SAR grounded in the findings and retrieved policy."
        # The draft is for HUMAN review, so we keep confidence moderate by design.
        confidence = 0.85

        return {
            "sar_draft": draft,
            "cot_traces": [self.trace(reasoning, confidence)],
            "audit": stamp(f"{self.label} generated report"),
        }


sar_drafting = SARDraftingAgent()
