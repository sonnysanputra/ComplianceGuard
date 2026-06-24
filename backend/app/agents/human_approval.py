"""
4.9 Human Approval node

Pauses the graph (human-in-the-loop). Deliberately a plain function, NOT a
BaseAgent: interrupt() raises a control signal to suspend the graph, and the
BaseAgent wrapper's try/except + retry would interfere with that pause.
"""

from langgraph.types import interrupt
from app.core.state import stamp


def human_approval(state: dict) -> dict:
    decision = interrupt({
        "risk_score": state.get("risk_score"),
        "recommendation": state.get("recommendation"),
        "sar_draft": state.get("sar_draft", ""),
        "review": state.get("review", {}),
    })

    return {
        "human_decision": decision,
        "cot_traces": [{
            "agent": "human_approval",
            "reasoning": f"Human analyst decision: {decision}",
            "confidence": 1.0,
            "output": {"decision": decision},
            "duration_ms": 0,
        }],
        "a2a_messages": [{"from": "human_approval", "status": "ok", "confidence": 1.0}],
        "audit": stamp(f"Human analyst decision: {decision}"),
    }
