"""
4.6 Risk Scoring Agent (hybrid: deterministic baseline + Qwen judgment)

A transparent weighted score gives an auditable BASELINE (and a safety anchor).
Qwen independently assesses the same findings and returns its own score + risk
level + reasoning. The final score BLENDS both -- so the LLM genuinely drives
the judgment, while the rule score keeps it grounded and explainable.
"""

from app.agents.base import BaseAgent
from app.core.state import stamp


class RiskScoringAgent(BaseAgent):
    name = "risk_scoring"
    label = "Risk Scoring Agent"

    def run(self, state: dict) -> dict:
        tf = state["transaction_findings"]["flags"]
        typology = state["transaction_findings"].get("typology", "unknown")
        kf = state["kyc_findings"]
        wf = state["watchlist_findings"]
        policies = state.get("retrieved_policies", [])

        # ---- 1. Deterministic baseline (transparent, auditable anchor) ----
        rule_score = 0
        if tf.get("money_mule"):             rule_score += 30
        if tf.get("structuring"):            rule_score += 25
        if tf.get("rapid_dispersion"):       rule_score += 25
        if tf.get("new_overseas_recipient"): rule_score += 15
        if tf.get("volume_spike"):           rule_score += 15
        if kf["income_mismatch"]:            rule_score += 20
        if wf["is_match"]:                   rule_score += 25
        if wf["high_risk_country"]:          rule_score += 10
        if kf["previous_alerts"] > 0:        rule_score += 10
        rule_score = min(rule_score, 100)

        # ---- 2. Qwen's independent AI risk assessment ----
        assessment = self.think(
            system=("You are an AML risk officer. Assess money-laundering risk from "
                    "the investigation findings and the relevant policy. Be objective."),
            prompt=(f"Typology: {typology}\n"
                    f"Transaction flags: {tf}\n"
                    f"KYC: income mismatch={kf['income_mismatch']}, "
                    f"prior alerts={kf['previous_alerts']}\n"
                    f"Watchlist: match={wf['is_match']}, high-risk country={wf['high_risk_country']}\n"
                    f"Relevant policy: {policies[0] if policies else 'none'}\n"
                    f"Rule-based baseline score: {rule_score}/100\n\n"
                    'Return JSON: {"ai_score": <0-100>, "risk_level": '
                    '"LOW|MEDIUM|HIGH|CRITICAL", "confidence": <0-100>, '
                    '"reasoning": "<3 sentence explanation>"}'),
        )

        # ---- 3. Blend: AI drives the judgment, rules anchor it ----
        ai_score = int(assessment.get("ai_score", rule_score))
        final_score = round((rule_score + ai_score) / 2)
        risk_level = self._level(final_score)   # derived from the score, always consistent
        explanation = assessment.get("reasoning") or (
            f"Combined rule ({rule_score}) and AI ({ai_score}) assessment.")
        confidence = float(assessment.get("confidence", 85)) / 100.0

        rec = ("Escalate to Level 2 and prepare SAR draft" if final_score >= 60
               else "Monitor / close as low risk")

        return {
            "risk_score": final_score,
            "rule_score": rule_score,
            "ai_score": ai_score,
            "risk_level": risk_level,
            "recommendation": rec,
            "risk_explanation": explanation,
            "cot_traces": [self.trace(explanation, confidence,
                                      output={"final": final_score, "rule": rule_score,
                                              "ai": ai_score, "level": risk_level})],
            "audit": stamp(f"{self.label} scored {final_score}/100 "
                           f"(rule {rule_score}, AI {ai_score}) -> {risk_level}"),
        }

    @staticmethod
    def _level(score: int) -> str:
        if score >= 80:  return "CRITICAL"
        if score >= 60:  return "HIGH"
        if score >= 35:  return "MEDIUM"
        return "LOW"


risk_scoring = RiskScoringAgent()
