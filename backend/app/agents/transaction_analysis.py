"""
4.2 Transaction Analysis Agent (hybrid: rules ground the facts, Qwen detects)

Pure Python AGGREGATES the transaction facts (counts, amounts, timing, in/out
flows) -- these are objective numbers, not judgments. Qwen then REASONS over
those facts to identify the AML typology and red flags. Deterministic flags are
kept as a grounding signal + safety fallback if the LLM response can't be parsed.
"""

from datetime import datetime

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.tools.db import get_transactions, HIGH_RISK_COUNTRIES

REPORTING_THRESHOLD = 10_000   # RM -- amounts just under this suggest structuring

SYSTEM_PROMPT = """You are a senior AML transaction analyst at a bank, reviewing a \
flagged customer's activity.

YOUR JOB
Explain the suspicious pattern and list the specific red flags, reasoning ONLY from
the facts and computed signals provided. Never invent data. Do not describe a country
as high-risk unless it appears in the provided high_risk_countries list.

MONEY-LAUNDERING TYPOLOGIES (what each looks like)
- structuring          : repeated transfers kept just under the reporting threshold
- money mule           : large inbound funds rapidly forwarded to several new recipients
- layering / dispersion: funds split across many newly added recipients in a short window
- high-risk overseas   : transfers to flagged jurisdictions
- volume spike         : activity far above the customer's own historical baseline

Each red flag must be a concrete, fact-based observation (cite the number), not a generic phrase.
"""


class TransactionAnalysisAgent(BaseAgent):
    name = "transaction_analysis"
    label = "Transaction Analysis Agent"

    def run(self, state: dict) -> dict:
        cid = state["alert"]["customer_id"]
        txns = get_transactions(cid)                       # tool call, no cost

        # ---- 1. Aggregate objective FACTS (not detection -- just arithmetic) ----
        outgoing = [t for t in txns if t.get("direction", "out") == "out"]
        incoming = [t for t in txns if t.get("direction") == "in"]
        recent = [t for t in outgoing if t["is_new_recipient"]]
        total_recent = sum(t["amount"] for t in recent)
        distinct_recipients = len({t["recipient"] for t in recent})
        times = sorted(datetime.fromisoformat(t["date_time"]) for t in recent)
        window_hours = (times[-1] - times[0]).total_seconds() / 3600 if len(times) > 1 else 0
        historical = [t for t in outgoing if not t["is_new_recipient"]]
        avg_historical = (sum(t["amount"] for t in historical) / len(historical)
                          if historical else 0)
        incoming_total = sum(t["amount"] for t in incoming)
        amounts_recent = [t["amount"] for t in recent]
        countries = sorted({t["country"] for t in recent})

        facts = {
            "new_recipient_transfers": len(recent),
            "total_to_new_recipients": total_recent,
            "distinct_new_recipients": distinct_recipients,
            "window_hours": round(window_hours, 1),
            "individual_amounts": amounts_recent,
            "incoming_total": incoming_total,
            "customer_avg_transaction": round(avg_historical),
            "destination_countries": countries,
            "reporting_threshold": REPORTING_THRESHOLD,
            "high_risk_countries": sorted(HIGH_RISK_COUNTRIES),
        }

        # ---- 2. Deterministic flags: grounding signal + safety fallback ----
        rule_flags = {
            "structuring": sum(
                1 for a in amounts_recent if 0.9 * REPORTING_THRESHOLD <= a < REPORTING_THRESHOLD
            ) >= 3,
            "money_mule": bool(incoming) and len(recent) >= 2
                          and total_recent >= 0.6 * max(incoming_total, 1),
            "rapid_dispersion": distinct_recipients >= 5 and window_hours <= 48,
            "new_overseas_recipient": any(c in HIGH_RISK_COUNTRIES for c in countries),
            "volume_spike": total_recent > 10 * max(avg_historical, 1),
        }

        # Rules own the typology LABEL (reliable). Qwen owns the REASONING.
        typology = self._rule_typology(rule_flags)

        # ---- 3. Qwen reasons about the detected pattern (grounded in signals) ----
        analysis = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                f"DETECTED TYPOLOGY (from rules): {typology}\n\n"
                f"TRANSACTION FACTS:\n{facts}\n\n"
                f"COMPUTED SIGNALS (true = triggered):\n{rule_flags}\n\n"
                "Return ONLY this JSON (each red flag gets its own confidence):\n"
                "{\n"
                '  "reasoning": "<2-3 sentences on why this pattern is or is not suspicious>",\n'
                '  "red_flags": [\n'
                '    {"flag": "<concrete fact-based observation>", "confidence": <0-100>}\n'
                "  ],\n"
                '  "confidence": <0-100, your confidence the typology label is correct>\n'
                "}\n\n"
                f"{CONFIDENCE_RUBRIC}"
            ),
        )

        reasoning = analysis.get("reasoning") or f"Detected pattern: {typology}."
        # floor at 0.5 -- a clean (low-suspicion) finding shouldn't read as "no confidence"
        confidence = max(float(analysis.get("confidence", 80)) / 100.0, 0.5)
        llm_flags = analysis.get("red_flags", [])   # list of {flag, confidence}

        return {
            "transaction_findings": {
                "flags": rule_flags,            # reliable signal for risk scoring
                "typology": typology,           # rule-detected, Qwen-explained
                "llm_red_flags": llm_flags,
                "total_recent": total_recent,
                "distinct_recipients": distinct_recipients,
                "window_hours": round(window_hours, 1),
                "summary": reasoning,
            },
            "cot_traces": [self.trace(reasoning, confidence, output={"typology": typology})],
            "audit": stamp(f"{self.label} detected typology: {typology}"),
        }

    @staticmethod
    def _rule_typology(flags: dict) -> str:
        """Deterministic typology classification -- reliable, so it owns the label."""
        if flags["money_mule"]:             return "money mule"
        if flags["structuring"]:            return "structuring"
        if flags["rapid_dispersion"]:       return "layering/dispersion"
        if flags["new_overseas_recipient"]: return "high-risk overseas transfer"
        if flags["volume_spike"]:           return "volume spike"
        return "none"


transaction_analysis = TransactionAnalysisAgent()
