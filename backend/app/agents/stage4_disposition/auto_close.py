"""
4.x Auto-Clearance Agent

A low-risk case should not just silently end -- a compliance system records WHY
it was cleared. This produces a professional clearance note for the two auto-close
paths: a false positive cleared by the FP review, and a genuinely clean low-risk
case. The note states the reason, the supporting evidence, and the recommended
action, so the closure is auditable.

Deterministic (no LLM).
"""

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.tools.db import get_transactions


class AutoClearanceAgent(BaseAgent):
    name = "auto_close"
    label = "Auto-Clearance Agent"
    uses_llm = False

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        fp = state.get("fp_review") or {}
        wf = state.get("watchlist_findings") or {}
        am = state.get("adverse_media_findings") or {}
        mem = state.get("memory_findings") or {}
        checks = fp.get("checks") or {}
        txns = get_transactions(alert["customer_id"])
        recipient = (alert.get("recipient") or "").strip().lower()

        # ---- build the evidence behind the clearance ----
        evidence = []
        learned = mem.get("learned_suppression")
        if learned:
            evidence.append(
                f"Recipient '{learned.get('recipient')}' was cleared as a false positive "
                f"by an analyst on case {learned.get('source_case_id')}"
                + (" (different customer) — learned suppression applied"
                   if learned.get("cross_customer") else " — learned suppression applied"))
        paid_before = sum(1 for t in txns
                          if (t.get("recipient") or "").strip().lower() == recipient
                          and not t.get("is_new_recipient"))
        if paid_before:
            evidence.append(f"Recipient has been paid {paid_before} time(s) before")
        if alert.get("supporting_document") or any(t.get("supporting_document_url") for t in txns):
            evidence.append("Supporting document / invoice on file")
        if checks.get("economic_purpose_clear"):
            evidence.append("Clear economic purpose stated")
        if checks.get("amount_consistent"):
            evidence.append("Transaction amount is within historical range")

        watchlist_clear = not wf.get("is_match") and not any(
            (wf.get(p) or {}).get("verdict") == "POSSIBLE_MATCH_REQUIRES_REVIEW"
            for p in ("customer_screening", "recipient_screening"))
        if watchlist_clear:
            evidence.append("No watchlist or sanctions match")
        if not am.get("negative_news"):
            evidence.append("No adverse media found")
        if not state.get("risk_factors"):
            evidence.append("No AML typology detected; activity within the account baseline")
        if not evidence:
            evidence.append("No suspicious indicators detected")

        # ---- reason + recommended action ----
        clearance_reason = fp.get("clearance_reason") or (
            "Activity is consistent with the account's established behaviour and all "
            "screening is clear; no suspicious indicators were found.")
        # a cleared false positive keeps a light monitoring flag; a clean case needs nothing
        recommended = "Close with monitoring" if fp else "Close - no further action required"

        note = {
            "status": "LOW_RISK_AUTO_CLEARED",
            "clearance_reason": clearance_reason,
            "evidence": evidence,
            "recommended_action": recommended,
        }
        return {
            "clearance_note": note,
            "audit_rationales": [self.trace(clearance_reason, 0.9,
                                      evidence=evidence, output=note)],
            "audit": stamp(f"{self.label}: LOW_RISK_AUTO_CLEARED -- {recommended}"),
        }


auto_close = AutoClearanceAgent()
