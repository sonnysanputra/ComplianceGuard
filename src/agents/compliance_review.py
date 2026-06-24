"""
4.8 Compliance Review Agent

Quality-control gate: checks the SAR draft contains every required section.
Pure Python checklist -- confidence reflects how complete the report is.
"""

from .base import BaseAgent
from ..state import stamp


class ComplianceReviewAgent(BaseAgent):
    name = "compliance_review"
    label = "Compliance Review Agent"

    REQUIRED = ["Customer Information", "Suspicious Indicators",
                "Risk Assessment", "Recommended Action"]

    def run(self, state: dict) -> dict:
        draft = state.get("sar_draft", "")
        missing = [s for s in self.REQUIRED if s.lower() not in draft.lower()]
        complete = len(missing) == 0

        reasoning = (
            f"Checked {len(self.REQUIRED)} required SAR sections. "
            f"{'All present.' if complete else f'Missing: {missing}.'}"
        )
        confidence = round((len(self.REQUIRED) - len(missing)) / len(self.REQUIRED), 2)

        return {
            "review": {
                "complete": complete,
                "missing_sections": missing,
                "status": "Ready for human review",
            },
            "cot_traces": [self.trace(reasoning, confidence, output={"complete": complete})],
            "audit": stamp(f"{self.label} checked report completeness"),
        }


compliance_review = ComplianceReviewAgent()
