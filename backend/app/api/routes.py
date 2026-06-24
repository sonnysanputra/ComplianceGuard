"""
FastAPI layer -- exposes the investigation orchestrator over HTTP so a frontend
(or any client) can drive it. The agents/orchestrator are unchanged; this just
translates HTTP requests into graph calls.

Endpoints
  GET  /health                              -> liveness check
  GET  /scenarios                           -> demo alerts (for the case picker)
  POST /investigate                         -> run a case (pauses at HITL)
  GET  /cases                               -> list all investigated cases
  GET  /case/{id}                           -> full current state of a case
  GET  /case/{id}/audit                     -> the audit timeline
  GET  /case/{id}/sar                       -> the SAR draft text
  POST /case/{id}/decision                  -> approve / reject / edit / request_more_info
  POST /case/{id}/rerun-agent/{agent_name}  -> re-run a single agent on the case
  POST /case/{id}/export                    -> download the case as a Markdown report

State is kept per case by LangGraph's checkpointer (thread_id = case_id), so the
pause/resume works across separate HTTP requests within the running server.
"""

import app.core.config  # noqa: F401 -- loads .env first

import json
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.types import Command

from app.orchestrator import build_graph
from app.data.scenarios import SCENARIOS
from app.services.persistence import (
    persist_case, persist_decision, list_cases, get_case_events, get_case_sar,
)

# agent instances that are safe to re-run standalone (no human interrupt)
from app.agents.alert_intake import alert_intake
from app.agents.data_quality import data_quality
from app.agents.transaction_analysis import transaction_analysis
from app.agents.kyc_profile import kyc_profile
from app.agents.watchlist_screening import watchlist_screening
from app.agents.policy_rag import policy_rag
from app.agents.case_memory import case_memory
from app.agents.risk_scoring import risk_scoring

AGENTS = {a.name: a for a in [
    alert_intake, data_quality, transaction_analysis, kyc_profile,
    watchlist_screening, policy_rag, case_memory, risk_scoring,
]}

# human-readable labels for streamed progress events
LABELS = {
    "alert_intake": "Alert Intake Agent",
    "data_quality": "Data Quality Gate",
    "transaction_analysis": "Transaction Analysis Agent",
    "kyc_profile": "KYC Profile Agent",
    "watchlist_screening": "Watchlist Screening Agent",
    "policy_rag": "Policy RAG Agent",
    "case_memory": "Memory Agent",
    "risk_scoring": "Risk Scoring Agent",
    "sar_drafting": "SAR Drafting Agent",
    "compliance_review": "Compliance Review Agent",
    "human_approval": "Human Approval",
}

app = FastAPI(title="CompliGuard AI", version="1.0",
              description="Multi-agent AML compliance investigation API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# one graph for the process; the checkpointer holds each case's state in memory
graph = build_graph()


# ======================================================================
# Request / response models  (typed -> self-documenting in /docs)
# ======================================================================
class Alert(BaseModel):
    id: str
    customer_id: str
    reason: str
    recipient: Optional[str] = ""
    country: Optional[str] = ""
    total_amount: Optional[int] = 0
    num_transactions: Optional[int] = 0


class Decision(BaseModel):
    decision: Literal["approve", "reject", "request_more_info", "edit"]
    analyst_id: str
    analyst_note: Optional[str] = None
    edited_sar_draft: Optional[str] = None
    final_risk_level: Optional[str] = None
    rerun_targets: Optional[list[str]] = None


class CaseSnapshot(BaseModel):
    case_id: str
    status: str
    triage: Optional[dict] = None
    data_quality: Optional[dict] = None
    transaction_findings: Optional[dict] = None
    kyc_findings: Optional[dict] = None
    watchlist_findings: Optional[dict] = None
    memory_findings: Optional[dict] = None
    retrieved_policies: Optional[list] = None
    risk_score: Optional[int] = None
    rule_score: Optional[int] = None
    ai_score: Optional[int] = None
    risk_level: Optional[str] = None
    risk_factors: Optional[list] = None
    key_drivers: Optional[list] = None
    recommendation: Optional[str] = None
    risk_explanation: Optional[str] = None
    sar_draft: Optional[str] = None
    review: Optional[dict] = None
    human_decision: Optional[str] = None
    human_review: Optional[dict] = None
    errors: Optional[list] = None
    audit: Optional[list] = None
    cot_traces: Optional[list] = None
    a2a_messages: Optional[list] = None


class CaseSummary(BaseModel):
    case_id: str
    customer_id: Optional[str] = None
    typology: Optional[str] = None
    status: Optional[str] = None
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    updated_at: Optional[str] = None


class HealthResponse(BaseModel):
    status: str


class AuditResponse(BaseModel):
    case_id: str
    timeline: list[str]
    events: list[dict]


class SARResponse(BaseModel):
    case_id: str
    exists: bool
    sar_draft: Optional[str] = None


# ======================================================================
# Helpers
# ======================================================================
def _state(case_id: str) -> dict:
    v = graph.get_state({"configurable": {"thread_id": case_id}}).values
    if not v:
        raise HTTPException(status_code=404, detail=f"No case '{case_id}'")
    return v


def _snapshot(case_id: str) -> dict:
    """Serialize a case's current state."""
    cfg = {"configurable": {"thread_id": case_id}}
    state = graph.get_state(cfg)
    v = state.values
    if not v:
        raise HTTPException(status_code=404, detail=f"No case '{case_id}'")

    dq = v.get("data_quality", {})
    awaiting = "human_approval" in (state.next or ())
    if dq and not dq.get("complete", True):
        status = "needs_more_information"
    elif v.get("errors") and not v.get("human_decision"):
        status = "manual_review_required"
    elif awaiting:
        status = "awaiting_decision"
    elif v.get("human_decision"):
        status = "closed"
    else:
        status = "auto_closed"

    return {
        "case_id": case_id, "status": status,
        "triage": v.get("triage"), "data_quality": v.get("data_quality"),
        "transaction_findings": v.get("transaction_findings"),
        "kyc_findings": v.get("kyc_findings"),
        "watchlist_findings": v.get("watchlist_findings"),
        "memory_findings": v.get("memory_findings"),
        "retrieved_policies": v.get("retrieved_policies"),
        "risk_score": v.get("risk_score"), "rule_score": v.get("rule_score"),
        "ai_score": v.get("ai_score"), "risk_level": v.get("risk_level"),
        "risk_factors": v.get("risk_factors"), "key_drivers": v.get("key_drivers"),
        "recommendation": v.get("recommendation"),
        "risk_explanation": v.get("risk_explanation"),
        "sar_draft": v.get("sar_draft"), "review": v.get("review"),
        "human_decision": v.get("human_decision"),
        "human_review": v.get("human_review"), "errors": v.get("errors"),
        "audit": sorted(v.get("audit", [])),
        "cot_traces": v.get("cot_traces"), "a2a_messages": v.get("a2a_messages"),
    }


def _build_report(snap: dict) -> str:
    """Assemble a Markdown case report for export/download."""
    lines = [f"# Case Report — {snap['case_id']}", "",
             f"**Status:** {snap.get('status')}  ",
             f"**Risk:** {snap.get('risk_score')}/100 ({snap.get('risk_level')})  ",
             f"**Recommendation:** {snap.get('recommendation')}", ""]
    if snap.get("risk_factors"):
        lines += ["## Risk Factor Breakdown", ""]
        for f in snap["risk_factors"]:
            lines.append(f"- **{f.get('points'):+} {f.get('factor')}** — {f.get('evidence')}")
        lines.append("")
    if snap.get("sar_draft"):
        lines += ["## SAR Draft", "", snap["sar_draft"], ""]
    if snap.get("audit"):
        lines += ["## Audit Timeline", ""]
        lines += [f"- {a}" for a in snap["audit"]]
    return "\n".join(lines)


# ======================================================================
# Endpoints
# ======================================================================
@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.get("/scenarios")
def scenarios():
    return SCENARIOS


@app.post("/investigate", response_model=CaseSnapshot)
def investigate(alert: Alert):
    """Run the full investigation. Returns when the graph pauses for human
    approval (high risk) or ends (low risk / incomplete / tool failure)."""
    case_id = alert.id
    cfg = {"configurable": {"thread_id": case_id}}
    graph.invoke({"alert": alert.model_dump()}, cfg)
    snap = _snapshot(case_id)
    persist_case(graph.get_state(cfg).values, status=snap["status"])
    return snap


@app.post("/investigate/stream")
def investigate_stream(alert: Alert):
    """Run the investigation and STREAM agent progress as Server-Sent Events.
    Each agent emits a 'progress' event as it completes; a final 'done' event
    carries the status. Consume with fetch()+ReadableStream on the frontend.

    Event stream:
        event: progress   data: {agent, label, status, confidence, message}
        ...
        event: done        data: {case_id, status, risk_score, risk_level}
    """
    case_id = alert.id
    cfg = {"configurable": {"thread_id": case_id}}

    def gen():
        try:
            for chunk in graph.stream({"alert": alert.model_dump()}, cfg,
                                      stream_mode="updates"):
                for node, updates in chunk.items():
                    if node == "__interrupt__" or not isinstance(updates, dict):
                        continue
                    conf = None
                    if updates.get("cot_traces"):
                        conf = updates["cot_traces"][-1].get("confidence")
                    msg = updates["audit"][-1] if updates.get("audit") else ""
                    ev = {"agent": node, "label": LABELS.get(node, node),
                          "status": "completed", "confidence": conf, "message": msg}
                    yield f"event: progress\ndata: {json.dumps(ev)}\n\n"

            # investigation finished (paused for human, or ended)
            snap = _snapshot(case_id)
            persist_case(graph.get_state(cfg).values, status=snap["status"])
            done = {"case_id": case_id, "status": snap["status"],
                    "risk_score": snap.get("risk_score"),
                    "risk_level": snap.get("risk_level")}
            yield f"event: done\ndata: {json.dumps(done)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/cases", response_model=list[CaseSummary])
def cases(limit: int = 50):
    """List investigated cases (survives server restarts)."""
    return list_cases(limit)


@app.get("/case/{case_id}/status")
def case_status(case_id: str):
    """Lightweight status poll (for clients not using the SSE stream)."""
    snap = _snapshot(case_id)
    return {"case_id": case_id, "status": snap["status"],
            "risk_score": snap.get("risk_score"), "risk_level": snap.get("risk_level")}


@app.get("/case/{case_id}", response_model=CaseSnapshot)
def get_case(case_id: str):
    return _snapshot(case_id)


@app.get("/case/{case_id}/audit", response_model=AuditResponse)
def case_audit(case_id: str):
    """The audit timeline -- live (in memory) plus persisted events."""
    v = graph.get_state({"configurable": {"thread_id": case_id}}).values
    timeline = sorted(v.get("audit", [])) if v else []
    return {"case_id": case_id, "timeline": timeline, "events": get_case_events(case_id)}


@app.get("/case/{case_id}/sar", response_model=SARResponse)
def case_sar(case_id: str):
    """The SAR draft text (live state, falling back to the persisted copy)."""
    v = graph.get_state({"configurable": {"thread_id": case_id}}).values
    draft = (v or {}).get("sar_draft") or get_case_sar(case_id)
    return {"case_id": case_id, "exists": bool(draft), "sar_draft": draft}


@app.post("/case/{case_id}/decision", response_model=CaseSnapshot)
def decide(case_id: str, body: Decision):
    """Resume a paused case with the analyst's structured decision.
    'request_more_info' re-runs the investigation and pauses again."""
    cfg = {"configurable": {"thread_id": case_id}}
    graph.invoke(Command(resume=body.model_dump()), cfg)
    persist_decision(case_id, body.decision, analyst_id=body.analyst_id,
                     notes=body.analyst_note, final_risk_level=body.final_risk_level)
    snap = _snapshot(case_id)
    persist_case(graph.get_state(cfg).values, status=snap["status"])
    return snap


@app.post("/case/{case_id}/rerun-agent/{agent_name}", response_model=CaseSnapshot)
def rerun_agent(case_id: str, agent_name: str):
    """Re-run a single agent (e.g. watchlist_screening, policy_rag) on an existing
    case and merge its fresh output back in -- handy when a tool was flaky."""
    if agent_name not in AGENTS:
        raise HTTPException(status_code=404,
                            detail=f"Unknown agent '{agent_name}'. "
                                   f"Options: {sorted(AGENTS)}")
    cfg = {"configurable": {"thread_id": case_id}}
    v = _state(case_id)
    updates = AGENTS[agent_name](v)         # run just that agent
    graph.update_state(cfg, updates)        # merge into the checkpoint
    persist_case(graph.get_state(cfg).values, status=_snapshot(case_id)["status"])
    return _snapshot(case_id)


@app.post("/case/{case_id}/export")
def export_case(case_id: str):
    """Download the case as a Markdown report."""
    report = _build_report(_snapshot(case_id))
    return Response(
        content=report, media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{case_id}_report.md"'},
    )
