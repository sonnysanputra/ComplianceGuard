"""
4.x False Positive Review Agent

Real AML systems generate many false positives. Rather than auto-closing every
low-risk case (missing a real one) or escalating every alert (drowning analysts),
this agent runs a structured false-positive review on sub-threshold cases that
still triggered an alert, or where there is a possible watchlist name match.

It checks whether the activity is explainable -- known/established recipient,
supporting document, consistent amount, consistent profile, no list match -- and
decides whether the case can be auto-closed (with an audit note) or must go to a
human.

Important (per SC guidance on inadvertent same-name matches): a sanctions / PEP /
internal-blacklist name match is NEVER auto-cleared -- it always requires human
verification, even when the false-positive indicators are otherwise strong.
"""

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.rules.rule_engine import get_rules
from app.tools.db import get_customer, get_transactions

SYSTEM_PROMPT = """You are an AML false-positive reviewer. Given the alert and a set
of objective checks, judge how likely the alert is a false positive and give a short
clearance rationale. Use only the facts provided. A name match against a sanctions,
PEP, or internal-blacklist entry must still be verified by a human even if the other
indicators look benign (inadvertent same-name matches do occur)."""


class FalsePositiveReviewAgent(BaseAgent):
    name = "false_positive_review"
    label = "False Positive Review Agent"

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        recipient = (alert.get("recipient") or "").strip().lower()
        wf = state.get("watchlist_findings", {})
        kf = state.get("kyc_findings", {})

        cust = get_customer(alert["customer_id"])
        txns = get_transactions(alert["customer_id"])

        # ---- objective checks ----
        hist_to_recipient = [t for t in txns
                             if (t.get("recipient") or "").strip().lower() == recipient
                             and not t.get("is_new_recipient", False)]
        recipient_known = bool(hist_to_recipient) or bool(alert.get("recipient_known"))
        supporting_document = bool(alert.get("supporting_document"))
        amount = alert.get("total_amount", 0) or 0
        if hist_to_recipient:
            amount_consistent = amount <= 1.5 * max(t["amount"] for t in hist_to_recipient)
        else:
            amount_consistent = supporting_document   # documented new payment

        watchlist_possible = bool(wf.get("is_match")) or any(
            (wf.get(p) or {}).get("verdict") == "POSSIBLE_MATCH_REQUIRES_REVIEW"
            for p in ("customer_screening", "recipient_screening"))
        no_watchlist_match = not watchlist_possible
        profile_consistent = (kf.get("consistency") != "inconsistent"
                              and not kf.get("edd_required"))

        checks = {
            "recipient_known": recipient_known,
            "supporting_document_exists": supporting_document,
            "amount_consistent": amount_consistent,
            "no_watchlist_match": no_watchlist_match,
            "profile_consistent": profile_consistent,
        }

        # ---- Qwen assesses likelihood + clearance reason (grounded in checks) ----
        analysis = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                f"Alert: recipient={alert.get('recipient')}, amount=RM{amount}, "
                f"purpose='{alert.get('reason')}', supporting_document={alert.get('supporting_document')}\n"
                f"Checks: {checks}\n"
                f"Watchlist possible match: {watchlist_possible} "
                f"(list: {wf.get('list_type')})\n\n"
                'Return ONLY this JSON:\n'
                '{"false_positive_likelihood": "HIGH|MEDIUM|LOW", '
                '"clearance_reason": "<1-2 sentences>", "confidence": <0-100>}\n\n'
                f"{CONFIDENCE_RUBRIC}"
            ),
        )
        likelihood = (analysis.get("false_positive_likelihood") or self._heuristic(checks)).upper()
        clearance_reason = analysis.get("clearance_reason") or "Reviewed against false-positive criteria."
        confidence = float(analysis.get("confidence", 80)) / 100.0

        # ---- decision (with the sanctions-match safety override) ----
        fp_cfg = get_rules()["false_positive"]
        risk_adjustment = fp_cfg["risk_adjustment"] if likelihood == "HIGH" else 0

        if watchlist_possible:
            requires_human = True
            recommended = (f"Refer to compliance officer for "
                           f"{wf.get('list_type') or 'watchlist'} name-match verification.")
        elif likelihood == "HIGH" and profile_consistent and amount_consistent:
            requires_human = False
            recommended = "Auto-close with audit note."
        else:
            requires_human = True
            recommended = "Refer to human analyst for review."

        fp_review = {
            "checks": checks,
            "false_positive_likelihood": likelihood,
            "clearance_reason": clearance_reason,
            "risk_adjustment": risk_adjustment,
            "recommended_action": recommended,
            "requires_human_review": requires_human,
        }
        audit_msg = (f"{self.label}: FP likelihood {likelihood} -> "
                     f"{'human review' if requires_human else 'auto-close'}")
        updates = {
            "fp_review": fp_review,
            "audit_rationales": [self.trace(
                clearance_reason, confidence,
                evidence=[k.replace("_", " ") for k, v in checks.items() if v],
                output=fp_review)],
            "audit": stamp(audit_msg),
        }
        # a cleanly cleared false positive is the lowest priority (batch monitoring)
        if not requires_human:
            updates["priority"] = "P4"
            updates["priority_reason"] = f"Low risk with a strong false-positive " \
                                         f"explanation: {clearance_reason}"
        return updates

    @staticmethod
    def _heuristic(checks: dict) -> str:
        passed = sum(1 for v in checks.values() if v)
        return "HIGH" if passed >= 4 else "MEDIUM" if passed >= 2 else "LOW"


false_positive_review = FalsePositiveReviewAgent()
