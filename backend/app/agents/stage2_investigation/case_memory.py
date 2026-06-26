"""
4.10 Long-term Memory Agent

Looks up the customer's HISTORY across past investigations (persisted in Supabase)
plus their KYC alert record, giving the current case context it can't see on its
own: prior alerts, prior escalations, repeat recipients, past analyst decisions,
and whether the customer's flags have historically been confirmed or benign.

This is pure retrieval (DB lookups, no LLM). The risk_scoring agent then reasons
over this memory to raise the score for repeat offenders or lower it for
customers whose flags have consistently turned out to be false positives.
"""

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.core.evidence import EvidenceCollector
from app.tools.db import get_customer
from app.services.persistence import get_customer_history, get_learned_patterns


class CaseMemoryAgent(BaseAgent):
    name = "case_memory"
    label = "Memory Agent"
    uses_llm = False

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cid = alert["customer_id"]
        current_recipient = (alert.get("recipient") or "").strip().lower()

        cust = get_customer(cid)
        history = get_customer_history(cid, exclude_case_id=alert.get("id", ""))
        prior_cases = history["cases"]
        decisions = history["decisions"]

        # --- aggregate the memory signals (deterministic) ---
        previous_cases_found = len(prior_cases)
        previous_escalations = sum(
            1 for c in prior_cases if c.get("risk_level") in ("HIGH", "CRITICAL"))
        previous_false_positives = sum(
            1 for c in prior_cases
            if c.get("status") in ("LOW_RISK_AUTO_CLEARED", "auto_closed")   # +legacy rows
            or c.get("risk_level") == "LOW")
        same_recipient_seen_before = bool(current_recipient) and any(
            (c.get("recipient") or "").strip().lower() == current_recipient
            for c in prior_cases)
        human_overrides = sum(1 for d in decisions if d.get("decision") == "reject")
        baseline_prior_alerts = cust.get("previous_alerts", 0) if cust else 0

        # --- analyst feedback learning: did a human previously disagree with the AI? ---
        def tags(d):
            return d.get("feedback_tags") or []
        analyst_fp_overrides = sum(
            1 for d in decisions
            if "false_positive" in tags(d) or d.get("analyst_agrees_with_ai") is False)
        analyst_corrections = [d["corrected_typology"] for d in decisions
                               if d.get("corrected_typology")]
        feedback_tags = sorted({t for d in decisions for t in tags(d)})

        # --- CROSS-CUSTOMER learning: has the team already cleared this recipient? ---
        # Distilled false-positive feedback from ANY prior case (even a different
        # customer) suppresses a similar alert here -- with the original case cited.
        learned_suppression = self._match_learned_pattern(current_recipient, cid)

        # --- direction this memory should push the risk score ---
        # A confirmed escalation dominates; otherwise an explicit analyst false-positive
        # override -- on this customer OR a learned cross-customer pattern -- teaches the
        # system to LOWER risk on similar cases.
        if previous_escalations > 0:
            direction = "increase"
        elif analyst_fp_overrides > 0 or learned_suppression:
            direction = "reduce"
        elif same_recipient_seen_before:
            direction = "increase"
        elif previous_false_positives >= 2:
            direction = "reduce"
        else:
            direction = "neutral"

        if learned_suppression:
            signal = (f"Recipient '{learned_suppression['recipient']}' was cleared as a "
                      f"false positive by an analyst on case {learned_suppression['source_case_id']}"
                      + (" (a different customer)" if learned_suppression["cross_customer"] else "")
                      + ". Applying that learning to lower risk here.")
        else:
            signal = self._signal(previous_cases_found, previous_escalations,
                                  previous_false_positives, same_recipient_seen_before,
                                  human_overrides, baseline_prior_alerts,
                                  analyst_fp_overrides, analyst_corrections)

        # DB facts are certain, so confidence is high
        confidence = 0.9

        # ---- structured evidence from customer history ----
        coll = EvidenceCollector()
        ev_ids = []
        if previous_escalations:
            ev_ids.append(coll.add("memory", cid, "previous_escalations", previous_escalations,
                                   f"{previous_escalations} prior escalation(s) for this customer"))
        if same_recipient_seen_before:
            ev_ids.append(coll.add("memory", cid, "same_recipient_seen_before", True,
                                   "Same recipient seen in a previous investigation"))
        if previous_false_positives:
            ev_ids.append(coll.add("memory", cid, "previous_false_positives", previous_false_positives,
                                   f"{previous_false_positives} prior false positive(s) for this customer"))
        if analyst_fp_overrides:
            ev_ids.append(coll.add("memory", cid, "analyst_false_positive_feedback", analyst_fp_overrides,
                                   "Analyst previously overrode similar AI findings as a false positive"))
        if learned_suppression:
            ev_ids.append(coll.add(
                "analyst_note", learned_suppression["source_case_id"], "cleared_recipient",
                learned_suppression["recipient"],
                f"Analyst cleared '{learned_suppression['recipient']}' as a false positive "
                f"on case {learned_suppression['source_case_id']}"
                + (" (different customer)" if learned_suppression["cross_customer"] else "")))

        return {
            "memory_findings": {
                "previous_cases_found": previous_cases_found,
                "previous_escalations": previous_escalations,
                "previous_false_positives": previous_false_positives,
                "same_recipient_seen_before": same_recipient_seen_before,
                "human_overrides": human_overrides,
                "baseline_prior_alerts": baseline_prior_alerts,
                "analyst_false_positive_feedback": analyst_fp_overrides,
                "analyst_corrections": analyst_corrections,
                "analyst_feedback_tags": feedback_tags,
                "learned_suppression": learned_suppression,
                "memory_risk_direction": direction,
                "memory_risk_signal": signal,
                "evidence_ids": ev_ids,
            },
            "evidence": coll.items,
            "audit_rationales": [self.trace(signal, confidence,
                                      output={"direction": direction,
                                              "prior_cases": previous_cases_found})],
            "audit": stamp(f"{self.label} found {previous_cases_found} prior case(s), "
                           f"{previous_escalations} escalation(s) -> {direction}"),
        }

    @staticmethod
    def _match_learned_pattern(current_recipient: str, customer_id: str) -> dict | None:
        """Recall the team's accumulated false-positive feedback: if this alert's
        recipient was previously cleared by an analyst (on any customer), return the
        matching pattern so the system suppresses the alert and cites that decision."""
        if not current_recipient:
            return None
        for p in get_learned_patterns():
            if (p.get("recipient") or "").strip().lower() == current_recipient:
                return {
                    "recipient": p.get("recipient"),
                    "source_case_id": p.get("source_case_id"),
                    "source_customer_id": p.get("source_customer_id"),
                    "cross_customer": p.get("source_customer_id") != customer_id,
                    "typology": p.get("typology"),
                }
        return None

    @staticmethod
    def _signal(cases, escalations, false_pos, same_recipient, overrides, baseline,
                analyst_fp=0, corrections=None):
        # an explicit analyst false-positive override is the strongest learning signal
        if analyst_fp:
            msg = ("Previous AI recommendation was overridden by an analyst as a false "
                   "positive. Reduce confidence for similar cases.")
            if corrections:
                msg += f" Analyst corrected the typology to: {', '.join(sorted(set(corrections)))}."
            return msg
        if cases == 0 and baseline == 0:
            return "No prior history for this customer."
        parts = []
        if escalations:
            parts.append(f"{escalations} prior escalation(s)")
        if false_pos:
            parts.append(f"{false_pos} prior false positive(s)")
        if same_recipient:
            parts.append("same recipient seen in a previous case")
        if overrides:
            parts.append(f"{overrides} prior analyst override(s)")
        if baseline:
            parts.append(f"{baseline} alert(s) on the customer's KYC record")
        return "Customer history: " + ("; ".join(parts) if parts
                                       else f"{cases} prior case(s) on file") + "."


case_memory = CaseMemoryAgent()
