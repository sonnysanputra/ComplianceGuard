"""
Orchestrator -- the backend that wires the 9 agents into a LangGraph.

Flow (mirrors the proposal's high-level workflow):

  START
    -> alert_intake
        |-> transaction_analysis -|
        |-> kyc_profile           |  (run in parallel)
        |-> watchlist_screening   |
        |-> policy_rag            |
        |-> case_memory          -|  (long-term memory: customer history)
                -> risk_scoring
                    -> [score >= 60] sar_drafting -> compliance_review -> human_approval -> END
                    -> [score <  60] END   (low-risk early exit -- cost saver)
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# the investigation agents that run in parallel
INVESTIGATION = ["transaction_analysis", "transaction_timeline", "graph_analysis",
                 "kyc_profile", "watchlist_screening", "adverse_media_screening",
                 "policy_rag", "case_memory"]
MAX_MORE_INFO_ROUNDS = 2   # cap re-investigations so the loop can't run forever

from app.core.state import CaseState
from app.rules.rule_engine import get_rules
from app.agents.stage1_intake.alert_intake import alert_intake
from app.agents.stage1_intake.data_quality import data_quality
from app.agents.stage2_investigation.transaction_analysis import transaction_analysis
from app.agents.stage2_investigation.transaction_timeline import transaction_timeline
from app.agents.stage2_investigation.graph_analysis import graph_analysis
from app.agents.stage2_investigation.kyc_profile import kyc_profile
from app.agents.stage2_investigation.watchlist_screening import watchlist_screening
from app.agents.stage2_investigation.adverse_media_screening import adverse_media_screening
from app.agents.stage2_investigation.policy_rag import policy_rag
from app.agents.stage2_investigation.case_memory import case_memory
from app.agents.stage3_scoring.risk_scoring import risk_scoring
from app.agents.stage4_disposition.false_positive_review import false_positive_review
from app.agents.stage4_disposition.auto_close import auto_close
from app.agents.stage5_reporting.sar_drafting import sar_drafting
from app.agents.stage5_reporting.compliance_review import compliance_review
from app.agents.stage6_approval.human_approval import human_approval


# below this data-quality score we cannot score reliably -> stop the case
DATA_QUALITY_FLOOR = 60


def _watchlist_flagged(wf: dict) -> bool:
    """A confirmed OR possible watchlist / sanctions match on either party.
    A name match is never auto-cleared -- it always needs a human."""
    return bool(wf.get("is_match")) or any(
        (wf.get(p) or {}).get("verdict") == "POSSIBLE_MATCH_REQUIRES_REVIEW"
        for p in ("customer_screening", "recipient_screening"))


# FAIL-SAFE GATE. Critical data missing halts the case BEFORE investigation:
#   - customer/KYC profile missing      -> NEEDS_MORE_INFORMATION
#   - transaction history unavailable   -> NEEDS_MORE_INFORMATION
# (both are CRITICAL_MISSING in the data-quality agent -> can_continue = False).
def route_after_data_quality(state: CaseState):
    dq = state.get("data_quality", {})
    return INVESTIGATION if dq.get("can_continue", dq.get("complete", True)) else END


# FAIL-SAFE ROUTING after scoring -- strictest rules first. The system must
# NEVER auto-close a case it could not reliably assess:
#   1. data-quality score < 60          -> stop (request more information)
#   2. any tool failed (watchlist/RAG)  -> manual review (never auto-close on bad data)
#   3. high risk (>= threshold)         -> draft a SAR (still ends at human approval)
#   4. watchlist/sanctions match        -> manual review (never auto-cleared)
#   5. degraded (PARTIAL) data          -> manual review
#   6. sub-threshold but triggered      -> false-positive review
#   7. clean and low risk               -> auto-close
def route_after_scoring(state: CaseState):
    dq = state.get("data_quality", {})
    wf = state.get("watchlist_findings", {})

    # 1. data too poor to score reliably (safety net; the gate usually catches this)
    if dq.get("quality_score", 100) < DATA_QUALITY_FLOOR:
        return END

    # 2. a screening tool failed -> a human must review (no auto-close, no auto-SAR)
    if state.get("errors"):
        return "human_approval"

    # 3. high risk -> SAR drafting
    escalate_at = get_rules()["scoring"]["escalation_threshold"]
    if state.get("risk_score", 0) >= escalate_at:
        return "sar_drafting"

    # 4. a sanctions / watchlist match is never auto-cleared -> manual review
    if _watchlist_flagged(wf):
        return "human_approval"

    # 5. degraded data -> manual sign-off
    if dq.get("severity") == "PARTIAL":
        return "human_approval"

    # 6. sub-threshold but an alert triggered -> false-positive review
    if state.get("risk_factors"):
        return "false_positive_review"

    # 7. clean: nothing triggered -> auto-close (with a clearance note)
    return "auto_close"


# After the FP review: a clear false positive auto-closes (with a clearance note);
# anything else (incl. a sanctions/PEP name match) goes to a human.
def route_after_fp(state: CaseState):
    return ("human_approval" if state.get("fp_review", {}).get("requires_human_review")
            else "auto_close")


# After the human acts: 'request_more_info' re-runs the investigation (bounded),
# every other decision ends the case.
def route_after_approval(state: CaseState):
    if (state.get("human_decision") == "request_more_info"
            and state.get("more_info_rounds", 0) <= MAX_MORE_INFO_ROUNDS):
        targets = (state.get("human_review", {}) or {}).get("rerun_targets")
        targets = [t for t in (targets or []) if t in INVESTIGATION] or INVESTIGATION
        return targets        # fan back out to these investigation agents
    return END


def build_graph():
    g = StateGraph(CaseState)

    g.add_node("alert_intake", alert_intake)
    g.add_node("data_quality", data_quality)
    g.add_node("transaction_analysis", transaction_analysis)
    g.add_node("transaction_timeline", transaction_timeline)
    g.add_node("graph_analysis", graph_analysis)
    g.add_node("kyc_profile", kyc_profile)
    g.add_node("watchlist_screening", watchlist_screening)
    g.add_node("adverse_media_screening", adverse_media_screening)
    g.add_node("policy_rag", policy_rag)
    g.add_node("case_memory", case_memory)
    g.add_node("risk_scoring", risk_scoring)
    g.add_node("false_positive_review", false_positive_review)
    g.add_node("auto_close", auto_close)
    g.add_node("sar_drafting", sar_drafting)
    g.add_node("compliance_review", compliance_review)
    g.add_node("human_approval", human_approval)

    g.add_edge(START, "alert_intake")
    g.add_edge("alert_intake", "data_quality")

    # data quality gate: incomplete -> END (needs more info); complete -> investigate
    g.add_conditional_edges("data_quality", route_after_data_quality, INVESTIGATION + [END])

    # fan-in: the 5 investigation agents all feed risk scoring
    for node in INVESTIGATION:
        g.add_edge(node, "risk_scoring")

    g.add_conditional_edges("risk_scoring", route_after_scoring,
                            ["sar_drafting", "false_positive_review", "human_approval",
                             "auto_close", END])
    # FP review: clear false positive -> auto-close (clearance note); else -> human
    g.add_conditional_edges("false_positive_review", route_after_fp,
                            ["human_approval", "auto_close"])
    # auto-close emits a professional clearance note, then ends
    g.add_edge("auto_close", END)
    g.add_edge("sar_drafting", "compliance_review")
    g.add_edge("compliance_review", "human_approval")
    # human decision: request_more_info loops back to investigate; else END
    g.add_conditional_edges("human_approval", route_after_approval, INVESTIGATION + [END])

    return g.compile(checkpointer=MemorySaver())
