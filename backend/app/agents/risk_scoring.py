"""
4.6 Risk Scoring Agent (hybrid: deterministic baseline + Qwen judgment)

A transparent weighted score gives an auditable BASELINE (and a safety anchor).
Qwen independently assesses the same findings and returns its own score + risk
level + reasoning. The final score BLENDS both -- so the LLM genuinely drives
the judgment, while the rule score keeps it grounded and explainable.
"""

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp

SYSTEM_PROMPT = """You are an AML risk officer making an independent risk assessment \
of a flagged case.

YOUR JOB
Assess the money-laundering risk from the investigation findings and the cited
policy. You are a SECOND OPINION alongside a deterministic rule-based score -- agree
or disagree with it on the merits, reasoning only from the findings given.

SCORING GUIDE (0-100)
- 80-100 CRITICAL : multiple strong indicators (e.g. confirmed typology + watchlist hit + profile mismatch)
- 60-79  HIGH     : a clear typology or serious profile inconsistency
- 35-59  MEDIUM   : some concern but weak or partial evidence
- 0-34   LOW       : activity is explainable / likely a false positive

Identify the top 2-3 risk drivers. Do not invent findings that were not provided.
"""


class RiskScoringAgent(BaseAgent):
    name = "risk_scoring"
    label = "Risk Scoring Agent"

    def run(self, state: dict) -> dict:
        tf = state["transaction_findings"]["flags"]
        typology = state["transaction_findings"].get("typology", "unknown")
        kf = state["kyc_findings"]
        wf = state["watchlist_findings"]
        mem = state.get("memory_findings", {})
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

        # long-term memory adjustments (repeat offender raises, benign history lowers)
        if mem.get("previous_escalations", 0) > 0:       rule_score += 15
        if mem.get("same_recipient_seen_before"):        rule_score += 10
        if mem.get("memory_risk_direction") == "reduce": rule_score -= 10
        rule_score = max(0, min(rule_score, 100))

        # ---- 2. Qwen's independent AI risk assessment ----
        assessment = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                "INVESTIGATION FINDINGS\n"
                f"- detected typology     : {typology}\n"
                f"- transaction flags     : {tf}\n"
                f"- KYC consistency       : {kf.get('consistency', 'n/a')}; "
                f"key concern: {kf.get('key_concern', 'n/a')}; "
                f"EDD: {kf.get('edd_required')}\n"
                f"- income mismatch       : {kf['income_mismatch']}\n"
                f"- prior alerts          : {kf['previous_alerts']}\n"
                f"- watchlist             : match={wf['is_match']}, verdict={wf.get('verdict')}\n"
                f"- high-risk country     : {wf['high_risk_country']}\n"
                f"- LONG-TERM MEMORY      : {mem.get('memory_risk_signal', 'no prior history')}\n"
                f"- relevant policy       : {policies[0] if policies else 'none'}\n\n"
                f"RULE-BASED BASELINE SCORE: {rule_score}/100\n\n"
                "Return ONLY this JSON:\n"
                "{\n"
                '  "ai_score": <0-100>,\n'
                '  "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",\n'
                '  "key_drivers": ["<top driver>", "<next driver>"],\n'
                '  "confidence": <0-100>,\n'
                '  "reasoning": "<3 sentence explanation>"\n'
                "}\n\n"
                f"{CONFIDENCE_RUBRIC}"
            ),
        )

        # ---- 3. Blend: AI drives the judgment, rules anchor it ----
        ai_score = int(assessment.get("ai_score", rule_score))
        final_score = round((rule_score + ai_score) / 2)
        risk_level = self._level(final_score)   # derived from the score, always consistent
        explanation = assessment.get("reasoning") or (
            f"Combined rule ({rule_score}) and AI ({ai_score}) assessment.")
        key_drivers = assessment.get("key_drivers", [])
        confidence = float(assessment.get("confidence", 85)) / 100.0

        rec = ("Escalate to Level 2 and prepare SAR draft" if final_score >= 60
               else "Monitor / close as low risk")

        return {
            "risk_score": final_score,
            "rule_score": rule_score,
            "ai_score": ai_score,
            "risk_level": risk_level,
            "key_drivers": key_drivers,
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
