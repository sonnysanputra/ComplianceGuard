"""
FastAPI layer -- exposes the investigation orchestrator over HTTP so a frontend
(or any client) can drive it. The agents/orchestrator are unchanged; this just
translates HTTP requests into graph calls.

Endpoints
  GET  /health                     -> liveness check
  GET  /scenarios                  -> the demo alerts (for the case picker)
  POST /investigate                -> run a case; returns findings (pauses at HITL)
  GET  /case/{case_id}             -> current state of a case
  POST /case/{case_id}/decision    -> approve/reject/edit (resumes the graph)

State is kept per case by LangGraph's checkpointer (thread_id = case_id), so the
pause/resume works across separate HTTP requests within the running server.
"""

import app.core.config  # noqa: F401 -- loads .env first

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.types import Command

from app.orchestrator import build_graph
from app.data.scenarios import SCENARIOS

app = FastAPI(title="CompliGuard AI", version="1.0")

# allow the future frontend (any localhost port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# one graph for the process; the checkpointer holds each case's state in memory
graph = build_graph()


# ---- request bodies ----
class Alert(BaseModel):
    id: str
    customer_id: str
    reason: str
    recipient: str | None = ""
    country: str | None = ""
    total_amount: int | None = 0
    num_transactions: int | None = 0


class Decision(BaseModel):
    decision: str   # "approve" | "reject" | "edit"


def _snapshot(case_id: str) -> dict:
    """Serialize a case's current state for the frontend."""
    cfg = {"configurable": {"thread_id": case_id}}
    state = graph.get_state(cfg)
    v = state.values

    if not v:
        raise HTTPException(status_code=404, detail=f"No case '{case_id}'")

    awaiting = "human_approval" in (state.next or ())
    if awaiting:
        status = "awaiting_decision"
    elif v.get("human_decision"):
        status = "closed"
    else:
        status = "auto_closed"   # low-risk early exit

    return {
        "case_id": case_id,
        "status": status,
        "triage": v.get("triage"),
        "transaction_findings": v.get("transaction_findings"),
        "kyc_findings": v.get("kyc_findings"),
        "watchlist_findings": v.get("watchlist_findings"),
        "retrieved_policies": v.get("retrieved_policies"),
        "risk_score": v.get("risk_score"),
        "rule_score": v.get("rule_score"),
        "ai_score": v.get("ai_score"),
        "risk_level": v.get("risk_level"),
        "recommendation": v.get("recommendation"),
        "risk_explanation": v.get("risk_explanation"),
        "sar_draft": v.get("sar_draft"),
        "review": v.get("review"),
        "human_decision": v.get("human_decision"),
        "audit": sorted(v.get("audit", [])),
        "cot_traces": v.get("cot_traces"),
        "a2a_messages": v.get("a2a_messages"),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/scenarios")
def scenarios():
    return SCENARIOS


@app.post("/investigate")
def investigate(alert: Alert):
    """Run the full investigation. Returns when the graph pauses for human
    approval (high risk) or auto-closes (low risk). May take ~1-2 min."""
    case_id = alert.id
    cfg = {"configurable": {"thread_id": case_id}}
    graph.invoke({"alert": alert.model_dump()}, cfg)
    return _snapshot(case_id)


@app.get("/case/{case_id}")
def get_case(case_id: str):
    return _snapshot(case_id)


@app.post("/case/{case_id}/decision")
def decide(case_id: str, body: Decision):
    """Resume a paused case with the analyst's decision."""
    cfg = {"configurable": {"thread_id": case_id}}
    graph.invoke(Command(resume=body.decision), cfg)
    return _snapshot(case_id)
