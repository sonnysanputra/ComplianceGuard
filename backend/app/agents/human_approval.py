"""
4.9 Human Approval node

Pauses the graph (human-in-the-loop) and accepts a STRUCTURED decision, not just
a string. The analyst can:
  - approve            -> case escalated
  - reject             -> with a reason (analyst_note)
  - edit               -> supply an edited SAR draft (stored, overrides the AI draft)
  - request_more_info  -> re-run the investigation (the orchestrator loops back)
and can override the final risk level. Everything is recorded for audit.

Deliberately a plain function, NOT a BaseAgent: interrupt() raises a control
signal to suspend the graph, which the BaseAgent wrapper would interfere with.
"""

from langgraph.types import interrupt
from app.core.state import stamp


def human_approval(state: dict) -> dict:
    payload = interrupt({
        "risk_score":     state.get("risk_score"),
        "risk_level":     state.get("risk_level"),
        "risk_factors":   state.get("risk_factors"),
        "recommendation": state.get("recommendation"),
        "sar_draft":      state.get("sar_draft", ""),
        "review":         state.get("review", {}),
    })

    # the resume value -- a dict in the new API, or a bare string (legacy/CLI)
    if isinstance(payload, str):
        payload = {"decision": payload}

    decision = payload.get("decision", "approve")
    analyst_id = payload.get("analyst_id", "unknown")
    note = payload.get("analyst_note")

    updates = {
        "human_decision": decision,
        "human_review": {
            "decision":               decision,
            "analyst_id":             analyst_id,
            "analyst_note":           note,
            "final_risk_level":       payload.get("final_risk_level"),
            "edited":                 bool(payload.get("edited_sar_draft")),
            "rerun_targets":          payload.get("rerun_targets"),
            # analyst feedback -> feeds learning in the Case Memory Agent
            "analyst_agrees_with_ai": payload.get("analyst_agrees_with_ai"),
            "corrected_typology":     payload.get("corrected_typology"),
            "corrected_reason":       payload.get("corrected_reason"),
            "feedback_tags":          payload.get("feedback_tags"),
        },
        "a2a_messages": [{"from": "human_approval", "status": "ok", "confidence": 1.0}],
    }

    # apply an analyst-edited SAR draft (overrides the AI-generated one)
    if payload.get("edited_sar_draft"):
        updates["sar_draft"] = payload["edited_sar_draft"]

    # apply an analyst override of the risk level
    if payload.get("final_risk_level"):
        updates["risk_level"] = payload["final_risk_level"]

    # count re-investigation requests so the loop is bounded
    if decision == "request_more_info":
        updates["more_info_rounds"] = state.get("more_info_rounds", 0) + 1

    audit_msg = f"Human analyst ({analyst_id}) decision: {decision}"
    if note:
        audit_msg += f" — {note}"
    updates["audit"] = stamp(audit_msg)
    from app.core.governance import governance
    updates["audit_rationales"] = [{
        "agent": "human_approval",
        "rationale": audit_msg,
        "confidence": 1.0,
        "evidence": [note] if note else [],
        "output": {"decision": decision, "override": payload.get("final_risk_level")},
        "duration_ms": 0,
        **governance("human_approval_v1", uses_llm=False),   # human decision: model_name=None
    }]
    return updates
