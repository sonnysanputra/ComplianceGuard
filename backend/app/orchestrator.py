"""
Orchestrator -- the backend that wires the 9 agents into a LangGraph.

Flow (mirrors the proposal's high-level workflow):

  START
    -> alert_intake
        |-> transaction_analysis -|
        |-> kyc_profile           |  (run in parallel)
        |-> watchlist_screening   |
        |-> policy_rag           -|
                -> risk_scoring
                    -> [score >= 60] sar_drafting -> compliance_review -> human_approval -> END
                    -> [score <  60] END   (low-risk early exit -- cost saver)
"""

from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import CaseState
from app.agents.alert_intake import alert_intake
from app.agents.transaction_analysis import transaction_analysis
from app.agents.kyc_profile import kyc_profile
from app.agents.watchlist_screening import watchlist_screening
from app.agents.policy_rag import policy_rag
from app.agents.risk_scoring import risk_scoring
from app.agents.sar_drafting import sar_drafting
from app.agents.compliance_review import compliance_review
from app.agents.human_approval import human_approval


# Low-risk cases exit BEFORE the expensive SAR drafting node.
def route_after_scoring(state: CaseState) -> Literal["sar_drafting", "__end__"]:
    return "sar_drafting" if state["risk_score"] >= 60 else END


def build_graph():
    g = StateGraph(CaseState)

    g.add_node("alert_intake", alert_intake)
    g.add_node("transaction_analysis", transaction_analysis)
    g.add_node("kyc_profile", kyc_profile)
    g.add_node("watchlist_screening", watchlist_screening)
    g.add_node("policy_rag", policy_rag)
    g.add_node("risk_scoring", risk_scoring)
    g.add_node("sar_drafting", sar_drafting)
    g.add_node("compliance_review", compliance_review)
    g.add_node("human_approval", human_approval)

    g.add_edge(START, "alert_intake")

    # fan-out: 4 investigation agents run in parallel after intake
    for node in ["transaction_analysis", "kyc_profile",
                 "watchlist_screening", "policy_rag"]:
        g.add_edge("alert_intake", node)
        g.add_edge(node, "risk_scoring")   # fan-in: risk waits for all 4

    g.add_conditional_edges("risk_scoring", route_after_scoring)
    g.add_edge("sar_drafting", "compliance_review")
    g.add_edge("compliance_review", "human_approval")
    g.add_edge("human_approval", END)

    return g.compile(checkpointer=MemorySaver())
