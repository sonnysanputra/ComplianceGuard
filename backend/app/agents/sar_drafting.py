"""
4.7 SAR Drafting Agent

Generates the Suspicious Activity Report draft for human review. This is the one
node where the LLM genuinely earns its keep (real writing), so it uses self.llm.
"""

from app.agents.base import BaseAgent
from app.core.state import stamp

SYSTEM_PROMPT = """You are a financial-crime compliance officer drafting a Suspicious \
Activity Report (SAR) for a human analyst to review and approve.

RULES (strict)
- Use ONLY the facts provided. Do NOT invent names, amounts, accounts, or events.
- Do NOT call a country high-risk unless the findings say so.
- Only reference a typology that matches the DETECTED TYPOLOGY.
- Write in a formal, factual, regulatory tone. No speculation beyond the evidence.
- Cite the relevant policy where it supports an indicator.

STRUCTURE (use these exact section headings)
1. Customer Information
2. Alert Summary
3. Suspicious Indicators   (bullet points, each tied to a specific fact)
4. Risk Assessment         (state the score, level, and key drivers)
5. Recommended Action
"""


class SARDraftingAgent(BaseAgent):
    name = "sar_drafting"
    label = "SAR Drafting Agent"

    def run(self, state: dict) -> dict:
        draft = self.llm(
            system=SYSTEM_PROMPT,
            prompt=(
                "INVESTIGATION FINDINGS\n"
                f"- Alert            : {state['alert']}\n"
                f"- Detected typology: {state['transaction_findings'].get('typology')}\n"
                f"- Transaction notes: {state['transaction_findings']['summary']}\n"
                f"- KYC              : {state['kyc_findings']}\n"
                f"- Watchlist        : {state['watchlist_findings']}\n"
                f"- Risk             : {state['risk_score']}/100 ({state.get('risk_level')}); "
                f"drivers: {state.get('key_drivers')}\n"
                f"- Risk reasoning   : {state['risk_explanation']}\n"
                f"- Policy basis     : {state.get('retrieved_policies')}\n\n"
                "Write the SAR draft now."
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
