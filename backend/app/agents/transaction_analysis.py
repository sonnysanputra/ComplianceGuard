"""
4.2 Transaction Analysis Agent (hybrid: rules ground the facts, Qwen detects)

Pure Python AGGREGATES the transaction facts (counts, amounts, timing, in/out
flows) -- these are objective numbers, not judgments. Qwen then REASONS over
those facts to identify the AML typology and red flags. Deterministic flags are
kept as a grounding signal + safety fallback if the LLM response can't be parsed.
"""

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.rules.rule_engine import detect_transaction_typology
from app.tools.db import get_transactions

# Deterministic detection is owned by the AML rule engine (app/rules/). This
# agent calls the engine for the typology, then has Qwen reason about it. The
# engine's thresholds are demo/internal-review values, NOT a legal reporting
# threshold -- suspicion is contextual, not amount alone.

SYSTEM_PROMPT = """You are a senior AML transaction analyst at a bank, reviewing a \
flagged customer's activity.

YOUR JOB
Explain the suspicious pattern and list the specific red flags, reasoning ONLY from
the facts and computed signals provided. Never invent data. Do not describe a country
as high-risk unless it appears in the provided high_risk_countries list.

MONEY-LAUNDERING TYPOLOGIES (what each looks like)
- structuring          : repeated transfers kept just under the institution's internal review threshold
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
        txns = get_transactions(cid)                        # tool call, no cost

        # ---- 1. Deterministic detection is delegated to the RULE ENGINE ----
        det = detect_transaction_typology(txns)
        typology = det["typology"]
        facts = {
            "new_recipient_transfers": len(det["amounts_recent"]),
            "total_to_new_recipients": det["total_recent"],
            "distinct_new_recipients": det["distinct_recipients"],
            "window_hours": det["window_hours"],
            "individual_amounts": det["amounts_recent"],
            "incoming_total": det["incoming_total"],
            "customer_avg_transaction": det["avg_historical"],
            "destination_countries": det["destination_countries"],
        }

        # ---- 2. Qwen reasons about the detected pattern (grounded in signals) ----
        analysis = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                f"DETECTED TYPOLOGY (from rules): {typology}\n\n"
                f"TRANSACTION FACTS:\n{facts}\n\n"
                f"COMPUTED SIGNALS (true = triggered):\n{det['flags']}\n\n"
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
                "flags": det["flags"],          # reliable signal for risk scoring
                "typology": typology,           # rule-detected, Qwen-explained
                "llm_red_flags": llm_flags,
                "total_recent": det["total_recent"],
                "distinct_recipients": det["distinct_recipients"],
                "window_hours": det["window_hours"],
                "summary": reasoning,
            },
            "audit_rationales": [self.trace(
                reasoning, confidence,
                evidence=[f.get("flag") for f in llm_flags
                          if isinstance(f, dict) and f.get("flag")],
                output={"typology": typology})],
            "audit": stamp(f"{self.label} detected typology: {typology}"),
        }


transaction_analysis = TransactionAnalysisAgent()
