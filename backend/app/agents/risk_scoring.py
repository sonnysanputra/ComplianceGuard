"""
4.6 Risk Scoring Agent (hybrid: deterministic baseline + Qwen judgment)

A transparent weighted score gives an auditable BASELINE (and a safety anchor).
Qwen independently assesses the same findings and returns its own score + risk
level + reasoning. The final score BLENDS both -- so the LLM genuinely drives
the judgment, while the rule score keeps it grounded and explainable.
"""

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.rules.rule_engine import evaluate_aml_rules, get_rules
from app.tools.db import get_customer, get_transactions

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
        # ---- 0. Error policy: if any investigation tool failed, do NOT score
        #         blind -- escalate the case for manual human review. ----
        errors = state.get("errors", [])
        if errors:
            failed = sorted({e.get("agent") for e in errors})
            explanation = (f"Investigation tool(s) failed: {', '.join(failed)}. "
                           f"Automated scoring is unreliable; manual review required.")
            return {
                "risk_score": 0, "rule_score": 0, "ai_score": 0,
                "risk_level": "MANUAL_REVIEW_REQUIRED",
                "risk_factors": [], "key_drivers": [],
                "recommendation": "Escalate for manual review - one or more "
                                  "investigation tools failed.",
                "risk_explanation": explanation,
                "cot_traces": [self.trace(explanation, 0.0, output={"failed": failed})],
                "audit": stamp(f"{self.label} -> MANUAL_REVIEW_REQUIRED "
                               f"({', '.join(failed)} failed)"),
            }

        kf = state["kyc_findings"]
        wf = state["watchlist_findings"]
        mem = state.get("memory_findings", {})
        policies = state.get("retrieved_policies", [])
        alert = state["alert"]

        # ---- 1. Deterministic detection + scoring is delegated to the RULE ENGINE ----
        # The engine returns the triggered AML rules (id, name, points, severity,
        # evidence) plus the total rule score and typology -- a fully justifiable
        # breakdown. Risk scoring only blends this with the LLM and decides routing.
        customer = get_customer(alert["customer_id"])
        transactions = get_transactions(alert["customer_id"])
        result = evaluate_aml_rules(customer, transactions, wf, mem, alert)

        tf = result.flags
        typology = result.typology
        rule_score = result.total_rule_score
        factors = [r.to_dict() for r in result.triggered_rules]

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
                f"- relevant policy       : "
                f"{(policies[0]['policy_id'] + ': ' + policies[0]['content']) if policies else 'none'}\n\n"
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

        escalate_at = get_rules()["scoring"]["escalation_threshold"]
        rec = ("Escalate to Level 2 and prepare SAR draft" if final_score >= escalate_at
               else "Monitor / close as low risk")

        return {
            "risk_score": final_score,
            "rule_score": rule_score,
            "ai_score": ai_score,
            "risk_level": risk_level,
            "risk_factors": factors,        # explainable breakdown: factor + points + evidence
            "key_drivers": key_drivers,
            "recommendation": rec,
            "risk_explanation": explanation,
            "cot_traces": [self.trace(explanation, confidence,
                                      output={"final": final_score, "rule": rule_score,
                                              "ai": ai_score, "level": risk_level,
                                              "factors": factors})],
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
