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

# the five investigation agents that run in parallel
INVESTIGATION = ["transaction_analysis", "kyc_profile",
                 "watchlist_screening", "policy_rag", "case_memory"]
MAX_MORE_INFO_ROUNDS = 2   # cap re-investigations so the loop can't run forever

from app.core.state import CaseState
from app.agents.alert_intake import alert_intake
from app.agents.data_quality import data_quality
from app.agents.transaction_analysis import transaction_analysis
from app.agents.kyc_profile import kyc_profile
from app.agents.watchlist_screening import watchlist_screening
from app.agents.policy_rag import policy_rag
from app.agents.case_memory import case_memory
from app.agents.risk_scoring import risk_scoring
from app.agents.sar_drafting import sar_drafting
from app.agents.compliance_review import compliance_review
from app.agents.human_approval import human_approval


# Incomplete cases halt here -- request more info instead of investigating blind.
def route_after_data_quality(state: CaseState):
    dq = state.get("data_quality", {})
    return INVESTIGATION if dq.get("complete", True) else END


# Routing after scoring:
#   tool failure  -> straight to human review (do NOT draft a SAR on bad data)
#   high risk     -> draft a SAR
#   low risk      -> end early
def route_after_scoring(state: CaseState):
    if state.get("errors"):
        return "human_approval"
    return "sar_drafting" if state.get("risk_score", 0) >= 60 else END


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
    g.add_node("kyc_profile", kyc_profile)
    g.add_node("watchlist_screening", watchlist_screening)
    g.add_node("policy_rag", policy_rag)
    g.add_node("case_memory", case_memory)
    g.add_node("risk_scoring", risk_scoring)
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
                            ["sar_drafting", "human_approval", END])
    g.add_edge("sar_drafting", "compliance_review")
    g.add_edge("compliance_review", "human_approval")
    # human decision: request_more_info loops back to investigate; else END
    g.add_conditional_edges("human_approval", route_after_approval, INVESTIGATION + [END])

    return g.compile(checkpointer=MemorySaver())
