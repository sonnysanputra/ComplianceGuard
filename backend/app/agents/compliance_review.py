"""
4.8 Compliance Review Agent (evidence validation + quality scoring)

Quality-control gate that goes beyond a section checklist:
  - confirms all required SAR sections are present (deterministic)
  - has Qwen validate that every claim in the draft is backed by an actual
    finding (flags invented / unsupported statements)
  - produces completeness + quality scores
  - decides whether the draft is ready for human review or needs revision
"""

from app.agents.base import BaseAgent
from app.core.state import stamp


class ComplianceReviewAgent(BaseAgent):
    name = "compliance_review"
    label = "Compliance Review Agent"

    REQUIRED = ["Customer Information", "Suspicious Indicators",
                "Risk Assessment", "Recommended Action"]

    def run(self, state: dict) -> dict:
        draft = state.get("sar_draft", "")

        # --- deterministic: required sections present? ---
        missing = [s for s in self.REQUIRED if s.lower() not in draft.lower()]
        completeness = round((len(self.REQUIRED) - len(missing)) / len(self.REQUIRED), 2)

        # --- the actual findings, for the LLM to validate claims against ---
        findings = {
            "typology": state["transaction_findings"].get("typology"),
            "risk_score": state.get("risk_score"),
            "risk_level": state.get("risk_level"),
            "watchlist_match": state["watchlist_findings"].get("is_match"),
            "watchlist_verdict": state["watchlist_findings"].get("verdict"),
            "kyc_checks_failed": state["kyc_findings"].get("checks_failed"),
            "edd_required": state["kyc_findings"].get("edd_required"),
            "policies": state.get("retrieved_policies", []),
        }

        # --- Qwen validates the draft only makes supported claims ---
        review = self.think(
            system=("You are a compliance QA reviewer. Verify the SAR draft only makes "
                    "claims that are supported by the findings. Flag any unsupported or "
                    "invented statements (e.g. calling a country high-risk when it isn't, "
                    "or citing a typology that wasn't detected). Score quality 0-100."),
            prompt=(f"Findings (ground truth): {findings}\n\n"
                    f"SAR draft:\n{draft[:1600]}\n\n"
                    'Return JSON: {"claims_supported": true/false, '
                    '"unsupported_claims": ["..."], "quality_score": <0-100>, '
                    '"confidence": <0-100>, "reasoning": "<2-3 sentences>"}'),
        )
        quality = int(review.get("quality_score", 80))
        unsupported = review.get("unsupported_claims", []) or []
        supported = bool(review.get("claims_supported", True))
        reasoning = review.get("reasoning") or "Reviewed SAR for completeness and support."
        confidence = float(review.get("confidence", 85)) / 100.0

        ready = (len(missing) == 0) and supported
        status = "Ready for human review" if ready else "Needs revision before review"

        return {
            "review": {
                "complete": len(missing) == 0,
                "missing_sections": missing,
                "completeness_score": completeness,
                "quality_score": quality,
                "claims_supported": supported,
                "unsupported_claims": unsupported,
                "status": status,
            },
            "cot_traces": [self.trace(reasoning, confidence,
                                      output={"quality": quality, "supported": supported})],
            "audit": stamp(f"{self.label} quality {quality}/100, "
                           f"{'claims supported' if supported else f'{len(unsupported)} unsupported claim(s)'}"),
        }


compliance_review = ComplianceReviewAgent()
