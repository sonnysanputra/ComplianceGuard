"""
4.6 Risk Scoring Agent

Combines all findings into a transparent weighted score (pure Python -- auditable,
no LLM needed for the number), then uses ONE LLM call to explain the score and
self-rate confidence.
"""

from .base import BaseAgent
from ..state import stamp


class RiskScoringAgent(BaseAgent):
    name = "risk_scoring"
    label = "Risk Scoring Agent"

    def run(self, state: dict) -> dict:
        tf = state["transaction_findings"]["flags"]
        kf = state["kyc_findings"]
        wf = state["watchlist_findings"]

        # transparent, auditable weighted score (no LLM for the number)
        score = 0
        if tf.get("money_mule"):             score += 30
        if tf.get("structuring"):            score += 25
        if tf.get("rapid_dispersion"):       score += 25
        if tf.get("new_overseas_recipient"): score += 15
        if tf.get("volume_spike"):           score += 15
        if kf["income_mismatch"]:            score += 20
        if wf["is_match"]:                   score += 25
        if wf["high_risk_country"]:          score += 10
        if kf["previous_alerts"] > 0:        score += 10
        score = min(score, 100)

        rec = ("Escalate to Level 2 and prepare SAR draft" if score >= 60
               else "Monitor / close as low risk")

        # one LLM call: explanation + confidence
        explanation, confidence = self.reason(
            system="You are an AML risk officer. Explain only from the facts given.",
            prompt=(f"Risk score: {score}/100. Flags: {tf}; income mismatch: "
                    f"{kf['income_mismatch']}; watchlist match: {wf['is_match']}. "
                    f"Relevant policy: {state.get('retrieved_policies', [''])[0]}. "
                    f"In 3 sentences, explain why this score was assigned."),
        )

        return {
            "risk_score": score,
            "recommendation": rec,
            "risk_explanation": explanation,
            "cot_traces": [self.trace(explanation, confidence, output={"score": score})],
            "audit": stamp(f"{self.label} assigned {score}/100"),
        }


risk_scoring = RiskScoringAgent()
