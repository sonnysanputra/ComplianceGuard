"""
Evaluate SAR draft quality (structure) against the golden cases.

Metric
  SAR_required_sections_present -- does the generated SAR package render all 12
  regulator-style sections, with the core sections populated (not empty)?

Structure is deterministic, so no live LLM is needed (the narrative is stubbed).

Run:  python evals/evaluate_sar_quality.py
"""

from _common import load_cases, build_state, pct
from app.agents.sar_drafting import SARDraftingAgent
from app.services.sar_render import sar_to_sections

REQUIRED = [
    "1. Case Information", "2. Customer Information", "3. Alert Trigger",
    "4. Transaction Timeline", "5. Suspicious Indicators",
    "6. KYC / Customer Profile Review",
    "7. Watchlist / Sanctions / Adverse Media Screening",
    "8. Policy References", "9. Risk Assessment", "10. AI Recommendation",
    "11. Human Analyst Decision", "12. Attachments / Supporting Evidence",
]
# sections that must carry real content for a high-risk SAR (not just a placeholder)
CORE = {"1. Case Information", "2. Customer Information", "3. Alert Trigger",
        "4. Transaction Timeline", "5. Suspicious Indicators", "9. Risk Assessment"}
_PLACEHOLDERS = {"None on file.", "None cited.", "No specific indicators identified.",
                 "No transaction records available.", "Pending human analyst review."}


def main() -> bool:
    # SARs are produced for escalated (high-risk) cases
    cases = [c for c in load_cases() if c["expected_route"] == "SAR_DRAFTED"]
    agent = SARDraftingAgent()

    print("=" * 78)
    print("SAR QUALITY (STRUCTURE) EVALUATION")
    print("=" * 78)
    complete = 0
    for c in cases:
        st = build_state(c)
        indicators = [f"{f.get('name')}: {f.get('evidence')}" for f in st["risk_factors"]] \
            or ["Activity flagged by the monitoring system."]
        pkg = agent._build_package(st, c["customer"], c["transactions"],
                                   indicators, "Deterministic narrative for eval.",
                                   "Escalate to a human analyst for STR determination.")
        sections = {title: lines for title, lines in sar_to_sections(pkg)}

        missing = [s for s in REQUIRED if s not in sections]
        empty_core = [s for s in CORE
                      if not [ln for ln in sections.get(s, []) if ln not in _PLACEHOLDERS]]
        ok = not missing and not empty_core
        complete += ok

        print(f"\n{c['case_id']}")
        print(f"  sections present : {len(sections)}/12  {'PASS' if not missing else 'MISSING ' + str(missing)}")
        print(f"  core populated   : {'PASS' if not empty_core else 'EMPTY ' + str(empty_core)}")

    n = len(cases)
    print("\n" + "=" * 78)
    print("METRICS")
    print("-" * 78)
    print(f"  SAR_required_sections_present : {pct(complete, n)}  ({complete}/{n})")
    print("=" * 78)
    print("RESULT:", "ALL SARS STRUCTURALLY COMPLETE" if complete == n else "SOME SARS INCOMPLETE")
    return complete == n


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
