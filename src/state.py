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
    transaction_findings: dict
    kyc_findings: dict
    watchlist_findings: dict
    retrieved_policies: list
    risk_score: int
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
