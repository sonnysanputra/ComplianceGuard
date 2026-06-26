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

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.core.governance import governance as _governance
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

# QA self-validation (folded in from the former Compliance Review Agent): the
# drafting agent checks its own draft only makes claims the findings support,
# before handing it to a human -- no separate node, one reporting step.
REVIEW_PROMPT = """You are a compliance QA reviewer checking a draft Suspicious Activity \
Report (SAR) before it reaches a human analyst.

Verify the draft makes ONLY claims supported by the investigation findings (the ground
truth). Flag any unsupported / invented statement -- e.g. calling a country high-risk
when it is not in the findings, citing a typology that was not detected, asserting a
watchlist hit when none was found, or stating a fact not present in the findings.
Then score the draft's quality (clarity, completeness, accuracy) from 0-100."""


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

        # ---- QA self-validation (folded-in Compliance Review): confirm the draft
        #      only makes evidence-backed claims before a human sees it ----
        review = self._self_review(state, draft_md)

        rationale = ("Assembled a structured 12-section SAR draft package grounded in the "
                     f"findings; self-review quality {review['quality_score']}/100, "
                     f"{'claims supported' if review['claims_supported'] else 'unsupported claims flagged'}.")
        return {
            "sar_package": package,
            "sar_draft": draft_md,           # rendered Markdown (display / persistence / export)
            "review": review,
            "audit_rationales": [self.trace(
                rationale, 0.85,
                evidence=[f"{len(indicators)} indicators", f"{len(policies)} policies cited",
                          f"quality {review['quality_score']}/100"],
                output={"quality": review["quality_score"],
                        "supported": review["claims_supported"]})],
            "audit": stamp(f"{self.label} drafted + self-reviewed SAR package "
                           f"({len(indicators)} indicators, quality {review['quality_score']}/100)"),
        }

    # ---- QA gate: required sections present + claims supported by findings ----
    REQUIRED_SECTIONS = ["Customer Information", "Suspicious Indicators",
                         "Risk Assessment", "Recommended Action"]

    def _self_review(self, state, draft: str) -> dict:
        missing = [s for s in self.REQUIRED_SECTIONS if s.lower() not in draft.lower()]
        completeness = round((len(self.REQUIRED_SECTIONS) - len(missing)) / len(self.REQUIRED_SECTIONS), 2)

        findings = {
            "typology": (state.get("transaction_findings") or {}).get("typology"),
            "risk_score": state.get("risk_score"),
            "risk_level": state.get("risk_level"),
            "watchlist_match": (state.get("watchlist_findings") or {}).get("is_match"),
            "watchlist_verdict": (state.get("watchlist_findings") or {}).get("verdict"),
            "kyc_checks_failed": (state.get("kyc_findings") or {}).get("checks_failed"),
            "edd_required": (state.get("kyc_findings") or {}).get("edd_required"),
            "cited_policies": [p.get("policy_id") for p in state.get("retrieved_policies", [])],
        }
        review = self.think(
            system=REVIEW_PROMPT,
            prompt=(
                f"FINDINGS (ground truth):\n{findings}\n\n"
                f"SAR DRAFT:\n{draft[:1600]}\n\n"
                "Return ONLY this JSON:\n"
                "{\n"
                '  "claims_supported": <true|false>,\n'
                '  "unsupported_claims": ["<any invented/unsupported statement>"],\n'
                '  "quality_score": <0-100>,\n'
                '  "confidence": <0-100>,\n'
                '  "reasoning": "<2-3 sentences>"\n'
                "}\n\n"
                f"{CONFIDENCE_RUBRIC}"
            ),
        )
        supported = bool(review.get("claims_supported", True))
        return {
            "complete": len(missing) == 0,
            "missing_sections": missing,
            "completeness_score": completeness,
            "quality_score": int(review.get("quality_score", 80)),
            "claims_supported": supported,
            "unsupported_claims": review.get("unsupported_claims", []) or [],
            "status": ("Ready for human review" if (not missing and supported)
                       else "Needs revision before review"),
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

        # Prefer the Transaction Timeline Agent's annotated timeline (with risk
        # notes); fall back to a bare chronological list if it didn't run.
        tl = (state.get("timeline_findings") or {}).get("timeline")
        if tl:
            timeline = tl
        else:
            timeline = sorted(
                ({"time": t.get("date_time"), "amount": t.get("amount"),
                  "recipient": t.get("recipient"), "country": t.get("country"),
                  "transaction_type": t.get("transaction_type"),
                  "direction": (t.get("direction") or "out").upper(),
                  "new_recipient": t.get("is_new_recipient")}
                 for t in txns),
                key=lambda t: t["time"] or "")

        attachments = ["Customer KYC file (system of record)",
                       "Transaction logs (core banking)"]
        if alert.get("supporting_document"):
            attachments.insert(0, f"Supporting document: {alert['supporting_document']}")

        return {
            "case_information": {
                "case_id": tri.get("case_id") or alert.get("id"),
                "alert_id": alert.get("id"),
                "alert_type": tri.get("alert_type"),
                "priority": state.get("priority") or tri.get("priority"),
                "priority_reason": state.get("priority_reason"),
                "status": "DRAFT - awaiting human analyst review",
                "report_type": "Draft investigation package (not an STR submission)",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "governance": (lambda g: f"model {g['model_name']} | "
                               f"ruleset {g['ruleset_version']} | "
                               f"policy {g['policy_version']}")(_governance("sar_drafting_v1")),
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
                "adverse_media_verdict": (state.get("adverse_media_findings") or {}).get("verdict"),
                "adverse_media_hits": "; ".join(
                    f"{h.get('title')} ({h.get('risk_level')})"
                    for h in (state.get("adverse_media_findings") or {}).get("all_hits", [])) or None,
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
                "confidence": f"{state.get('confidence'):.0%}" if state.get("confidence") is not None else None,
                "confidence_factors": "; ".join(state.get("confidence_factors") or []) or None,
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
            # the full structured evidence pool -- every claim is traceable to an ID
            "evidence_register": state.get("evidence", []),
        }

    @staticmethod
    def _fallback_indicators(state) -> list:
        """If the LLM response can't be parsed, build indicators from the triggered rules."""
        return [f"{f.get('name')}: {f.get('evidence')}"
                for f in (state.get("risk_factors") or [])] \
            or ["Activity flagged by the monitoring system; see risk assessment."]


sar_drafting = SARDraftingAgent()
