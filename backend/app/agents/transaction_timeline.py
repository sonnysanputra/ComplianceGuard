"""
4.x Transaction Timeline Agent

Reconstructs the case as a chronological, annotated timeline -- "what happened
first, then next" -- which is how an analyst actually reads a case. Each event
gets a plain-language risk note (first transfer to a new overseas recipient,
near-threshold transfer, rapid succession, large inbound funds, etc.).

Pure deterministic: the notes are derived from the same thresholds the rule
engine uses, so the timeline never contradicts the risk scoring. No LLM cost.

Consumed by: the SAR draft, the risk-scoring evidence, the audit export, and the
frontend investigation page.
"""

from datetime import datetime

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.core.evidence import EvidenceCollector
from app.rules.country_risk import high_risk_countries, is_high_risk
from app.rules.rule_engine import get_rules
from app.tools.db import get_transactions

HOME_COUNTRY = "Malaysia"
RAPID_HOURS = 6                 # transfers this close together read as "rapid succession"
_ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth",
             "Seventh", "Eighth", "Ninth", "Tenth"]


def _ordinal(n: int) -> str:
    return _ORDINALS[n - 1] if 1 <= n <= len(_ORDINALS) else f"{n}th"


class TransactionTimelineAgent(BaseAgent):
    name = "transaction_timeline"
    label = "Transaction Timeline Agent"

    def run(self, state: dict) -> dict:
        cid = state["alert"]["customer_id"]
        txns = get_transactions(cid)

        # near-threshold band comes from the same rule the engine uses
        trs = {r["typology"]: r for r in get_rules().get("typology_rules", [])}
        sc = (trs.get("structuring") or {}).get("conditions", {})
        threshold = sc.get("internal_review_threshold", 10000)
        near_lo = sc.get("amount_min_ratio_to_threshold", 0.9) * threshold
        mule_min = (trs.get("money_mule") or {}).get("conditions", {}).get("incoming_amount_min", 20000)
        high_risk = high_risk_countries()

        ordered = sorted(txns, key=lambda t: t.get("date_time") or "")

        timeline = []
        seen_recipients: set[str] = set()
        near_count = 0
        prev_out_time = None

        for t in ordered:
            amount = t.get("amount", 0)
            recipient = t.get("recipient", "")
            country = t.get("country", "")
            direction = (t.get("direction") or "out").upper()
            is_new = bool(t.get("is_new_recipient"))
            overseas = bool(country) and country != HOME_COUNTRY
            near = near_lo <= amount < threshold
            first_to_recipient = recipient not in seen_recipients
            when = t.get("date_time")

            rapid = False
            if direction == "OUT" and prev_out_time and when:
                try:
                    gap_h = (datetime.fromisoformat(when)
                             - datetime.fromisoformat(prev_out_time)).total_seconds() / 3600
                    rapid = 0 <= gap_h <= RAPID_HOURS
                except ValueError:
                    rapid = False

            if near:
                near_count += 1
            note = self._risk_note(direction, amount, country, recipient, is_new,
                                   overseas, near, near_count, first_to_recipient,
                                   rapid, high_risk, mule_min, threshold)

            timeline.append({
                "time": when,
                "transaction_id": t.get("transaction_id"),
                "direction": direction,
                "amount": amount,
                "recipient": recipient,
                "country": country,
                "transaction_type": t.get("transaction_type"),
                "new_recipient": is_new,
                "risk_note": note,
            })
            seen_recipients.add(recipient)
            if direction == "OUT":
                prev_out_time = when

        # events worth surfacing as risk evidence (everything but routine activity)
        notable = [e for e in timeline if not e["risk_note"].startswith("Routine")]

        # structured evidence: one item per notable event ('TL' namespace so the
        # timeline's transaction IDs don't collide with the analysis agent's)
        coll = EvidenceCollector(prefix="TL")
        for e in notable:
            coll.add("transaction", e.get("transaction_id") or e["time"], "risk_note",
                     e["amount"], e["risk_note"])
        first, last = (ordered[0].get("date_time"), ordered[-1].get("date_time")) if ordered else (None, None)
        summary = (f"{len(timeline)} transactions from {first} to {last}; "
                   f"{near_count} near-threshold, {len(notable)} notable events."
                   if timeline else "No transactions on file.")

        findings = {
            "timeline": timeline,
            "notable_events": [{"time": e["time"], "risk_note": e["risk_note"]} for e in notable],
            "first_event": first,
            "last_event": last,
            "summary": summary,
        }
        return {
            "timeline_findings": findings,
            "evidence": coll.items,
            "audit_rationales": [self.trace(
                summary, 0.95,
                evidence=[f"{e['time']}: {e['risk_note']}" for e in notable] or ["No notable events."])],
            "audit": stamp(f"{self.label} built a {len(timeline)}-event timeline"),
        }

    @staticmethod
    def _risk_note(direction, amount, country, recipient, is_new, overseas, near,
                   near_count, first_to_recipient, rapid, high_risk, mule_min, threshold) -> str:
        if direction == "IN":
            if amount >= mule_min:
                return f"Large incoming funds (RM{amount:,}) - potential mule inflow"
            return f"Incoming funds (RM{amount:,})"

        # outgoing
        if is_new and first_to_recipient and overseas:
            jur = "high-risk jurisdiction" if is_high_risk(country) else "overseas recipient"
            note = f"First transfer to new {jur} ({country})"
        elif near:
            note = f"{_ordinal(near_count)} near-threshold transfer (RM{amount:,}, just under RM{threshold:,})"
        elif is_new and first_to_recipient:
            note = f"First transfer to new recipient ({recipient})"
        elif amount >= threshold:
            note = f"High-value transfer (RM{amount:,}) to {recipient}"
        else:
            return f"Routine payment (RM{amount:,}) to {recipient}"

        if rapid:
            note += "; rapid succession"
        return note


transaction_timeline = TransactionTimelineAgent()
