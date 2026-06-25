"""
4.7 SAR Drafting Agent

Produces a STRUCTURED, regulator-style SAR as JSON first (the 12-section draft
investigation package), then renders it to Markdown. PDF/DOCX exports render from
the same structured package, so every format is consistent and easy to validate.

Most of the package is assembled DETERMINISTICALLY from the investigation state
(facts -> sections). Qwen writes only the narrative parts that need real prose:
the suspicious indicators, a short case narrative, and the recommended action --
each grounded strictly in the findings.

Per SC / FIED STR guidance this is framed as a DRAFT investigation package for a
human analyst, NOT an automatic STR submission (human_review_required is always true).
"""

from datetime import datetime

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.services.sar_render import sar_to_markdown
from app.tools.db import get_customer, get_transactions

SYSTEM_PROMPT = """You are a financial-crime compliance officer preparing the narrative \
parts of a Suspicious Activity Report (SAR) for a human analyst to review.

RULES (strict)
- Use ONLY the facts provided. Do NOT invent names, amounts, accounts, or events.
- Do NOT call a country high-risk unless the findings say so.
- Only reference the DETECTED TYPOLOGY given.
- Formal, factual, regulatory tone. No speculation beyond the evidence.
- Each suspicious indicator must cite a specific fact (an amount, a count, a name).
"""


class SARDraftingAgent(BaseAgent):
    name = "sar_drafting"
    label = "SAR Drafting Agent"

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cid = alert["customer_id"]
        cust = get_customer(cid) or {}
        txns = get_transactions(cid)
        tf = state.get("transaction_findings") or {}
        kyc = state.get("kyc_findings") or {}
        wl = state.get("watchlist_findings") or {}
        policies = state.get("retrieved_policies") or []

        refs = "\n".join(
            f"    - {p['policy_id']}: {p['title']} (section {p['section']})"
            for p in policies) or "    - none"

        # ---- Qwen writes only the narrative parts (grounded in facts) ----
        analysis = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                "INVESTIGATION FINDINGS\n"
                f"- Detected typology: {tf.get('typology')}\n"
                f"- Transaction notes: {tf.get('summary')}\n"
                f"- KYC review       : {kyc.get('consistency')}, "
                f"concern: {kyc.get('key_concern')}, EDD: {kyc.get('edd_required')}\n"
                f"- Watchlist        : {wl.get('verdict')} "
                f"(best {wl.get('match_score')}% on {wl.get('list_type')})\n"
                f"- Risk             : {state.get('risk_score')}/100 "
                f"({state.get('risk_level')}); drivers: {state.get('key_drivers')}\n"
                f"- Cited policies   :\n{refs}\n\n"
                "Return ONLY this JSON:\n"
                "{\n"
                '  "suspicious_indicators": ["<concrete, fact-cited indicator>", ...],\n'
                '  "narrative": "<2-4 sentence factual case narrative>",\n'
                '  "recommended_action": "<formal recommendation for the analyst>"\n'
                "}"
            ),
        )

        indicators = analysis.get("suspicious_indicators") or self._fallback_indicators(state)
        narrative = analysis.get("narrative") or f"Activity consistent with {tf.get('typology')}."
        recommended = analysis.get("recommended_action") or state.get("recommendation") \
            or "Escalate to a human analyst for STR determination."

        package = self._build_package(state, cust, txns, indicators, narrative, recommended)
        draft_md = sar_to_markdown(package)

        rationale = "Assembled a structured 12-section SAR draft package grounded in the findings."
        return {
            "sar_package": package,
            "sar_draft": draft_md,           # rendered Markdown (display / persistence / export)
            "audit_rationales": [self.trace(
                rationale, 0.85,
                evidence=[f"{len(indicators)} indicators", f"{len(policies)} policies cited"])],
            "audit": stamp(f"{self.label} drafted SAR package ({len(indicators)} indicators)"),
        }

    # ---- deterministic assembly: facts -> 12-section package ----
    @staticmethod
    def _build_package(state, cust, txns, indicators, narrative, recommended) -> dict:
        alert = state["alert"]
        tri = state.get("triage") or {}
        kyc = state.get("kyc_findings") or {}
        wl = state.get("watchlist_findings") or {}
        cs = wl.get("customer_screening") or {}
        rs = wl.get("recipient_screening") or {}

        timeline = sorted(
            ({"date": t.get("date_time"), "amount": t.get("amount"),
              "recipient": t.get("recipient"), "country": t.get("country"),
              "type": t.get("transaction_type"), "direction": t.get("direction"),
              "new_recipient": t.get("is_new_recipient")}
             for t in txns),
            key=lambda t: t["date"] or "")

        attachments = ["Customer KYC file (system of record)",
                       "Transaction logs (core banking)"]
        if alert.get("supporting_document"):
            attachments.insert(0, f"Supporting document: {alert['supporting_document']}")

        return {
            "case_information": {
                "case_id": tri.get("case_id") or alert.get("id"),
                "alert_id": alert.get("id"),
                "alert_type": tri.get("alert_type"),
                "priority": tri.get("priority"),
                "status": "DRAFT - awaiting human analyst review",
                "report_type": "Draft investigation package (not an STR submission)",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
            "customer_information": {
                "customer_id": alert.get("customer_id"),
                "name": cust.get("name"),
                "occupation": cust.get("occupation"),
                "declared_income": f"RM{cust.get('declared_income')}/month"
                                   if cust.get("declared_income") else None,
                "account_age_months": cust.get("account_age_months"),
                "risk_category": cust.get("risk_category"),
                "kyc_status": cust.get("kyc_status"),
                "country": cust.get("country"),
            },
            "alert_trigger": {
                "reason": alert.get("reason"),
                "recipient": alert.get("recipient"),
                "amount": f"RM{alert.get('total_amount', 0):,}",
                "jurisdiction": alert.get("country"),
                "num_transactions": alert.get("num_transactions"),
                "supporting_document": alert.get("supporting_document"),
            },
            "transaction_timeline": timeline,
            "suspicious_indicators": indicators,
            "kyc_review": {
                "consistency": kyc.get("consistency"),
                "key_concern": kyc.get("key_concern"),
                "income_ratio": f"{kyc.get('income_ratio')}x monthly income"
                                if kyc.get("income_ratio") else None,
                "checks_failed": kyc.get("checks_failed"),
                "edd_required": kyc.get("edd_required"),
            },
            "watchlist_screening": {
                "customer_verdict": cs.get("verdict"),
                "recipient_verdict": rs.get("verdict"),
                "best_match": wl.get("best_match"),
                "list_type": wl.get("list_type"),
                "match_score": f"{wl.get('match_score')}%" if wl.get("match_score") else None,
                "required_action": wl.get("required_action"),
            },
            "policy_references": [
                {"policy_id": p.get("policy_id"), "title": p.get("title"),
                 "section": p.get("section"), "source": p.get("source")}
                for p in (state.get("retrieved_policies") or [])],
            "risk_assessment": {
                "final_score": f"{state.get('risk_score')}/100",
                "rule_score": state.get("rule_score"),
                "ai_score": state.get("ai_score"),
                "risk_level": state.get("risk_level"),
                "key_drivers": state.get("key_drivers"),
                "explanation": state.get("risk_explanation"),
            },
            "ai_recommendation": {
                "recommended_action": recommended,
                "narrative": narrative,
                "human_review_required": True,
            },
            "human_analyst_decision": {},   # filled in after the human decides
            "attachments": attachments,
        }

    @staticmethod
    def _fallback_indicators(state) -> list:
        """If the LLM response can't be parsed, build indicators from the triggered rules."""
        return [f"{f.get('name')}: {f.get('evidence')}"
                for f in (state.get("risk_factors") or [])] \
            or ["Activity flagged by the monitoring system; see risk assessment."]


sar_drafting = SARDraftingAgent()
