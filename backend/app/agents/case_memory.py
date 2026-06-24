"""
4.x Long-term Memory Agent

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
from app.tools.db import get_customer
from app.services.persistence import get_customer_history


class CaseMemoryAgent(BaseAgent):
    name = "case_memory"
    label = "Memory Agent"

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
            if c.get("status") == "auto_closed" or c.get("risk_level") == "LOW")
        same_recipient_seen_before = bool(current_recipient) and any(
            (c.get("recipient") or "").strip().lower() == current_recipient
            for c in prior_cases)
        human_overrides = sum(1 for d in decisions if d.get("decision") == "reject")
        baseline_prior_alerts = cust.get("previous_alerts", 0) if cust else 0

        # --- direction this memory should push the risk score ---
        if previous_escalations > 0 or same_recipient_seen_before:
            direction = "increase"
        elif previous_false_positives >= 2 and previous_escalations == 0:
            direction = "reduce"
        else:
            direction = "neutral"

        signal = self._signal(previous_cases_found, previous_escalations,
                              previous_false_positives, same_recipient_seen_before,
                              human_overrides, baseline_prior_alerts)

        # DB facts are certain, so confidence is high
        confidence = 0.9

        return {
            "memory_findings": {
                "previous_cases_found": previous_cases_found,
                "previous_escalations": previous_escalations,
                "previous_false_positives": previous_false_positives,
                "same_recipient_seen_before": same_recipient_seen_before,
                "human_overrides": human_overrides,
                "baseline_prior_alerts": baseline_prior_alerts,
                "memory_risk_direction": direction,
                "memory_risk_signal": signal,
            },
            "cot_traces": [self.trace(signal, confidence,
                                      output={"direction": direction,
                                              "prior_cases": previous_cases_found})],
            "audit": stamp(f"{self.label} found {previous_cases_found} prior case(s), "
                           f"{previous_escalations} escalation(s) -> {direction}"),
        }

    @staticmethod
    def _signal(cases, escalations, false_pos, same_recipient, overrides, baseline):
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
