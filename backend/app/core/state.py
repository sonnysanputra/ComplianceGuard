"""
The shared case file that flows through every agent in the graph.

Each agent receives the CaseState, does its part, and returns a partial
update which LangGraph merges back in. The `audit` field uses an `add`
reducer so every agent can append a timestamped line to a single timeline.
"""

from datetime import datetime
from operator import add
from typing import TypedDict, Annotated


class CaseState(TypedDict, total=False):
    alert: dict
    case_summary: str
    triage: dict             # alert type, severity, priority, entities, routing
    memory_findings: dict    # long-term memory: this customer's history
    transaction_findings: dict
    kyc_findings: dict
    watchlist_findings: dict
    retrieved_policies: list
    risk_score: int          # final blended score (rules + AI)
    rule_score: int          # deterministic baseline
    ai_score: int            # Qwen's independent assessment
    risk_level: str          # LOW | MEDIUM | HIGH | CRITICAL (from Qwen)
    key_drivers: list        # top risk drivers (from Qwen)
    risk_explanation: str
    recommendation: str
    sar_draft: str
    review: dict
    human_decision: str

    # --- observability accumulators (each agent appends; never overwrites) ---
    audit: Annotated[list, add]         # timestamped human-readable timeline
    cot_traces: Annotated[list, add]    # per-agent reasoning + confidence
    a2a_messages: Annotated[list, add]  # agent-to-agent status + confidence log


def stamp(msg: str) -> list:
    """Return a one-item audit list with a timestamp (for the `audit` field)."""
    return [f"{datetime.now().strftime('%H:%M:%S')} - {msg}"]
