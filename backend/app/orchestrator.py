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
INVESTIGATION = ["transaction_analysis", "transaction_timeline", "kyc_profile",
                 "watchlist_screening", "policy_rag", "case_memory"]
MAX_MORE_INFO_ROUNDS = 2   # cap re-investigations so the loop can't run forever

from app.core.state import CaseState
from app.rules.rule_engine import get_rules
from app.agents.alert_intake import alert_intake
from app.agents.data_quality import data_quality
from app.agents.transaction_analysis import transaction_analysis
from app.agents.transaction_timeline import transaction_timeline
from app.agents.kyc_profile import kyc_profile
from app.agents.watchlist_screening import watchlist_screening
from app.agents.policy_rag import policy_rag
from app.agents.case_memory import case_memory
from app.agents.risk_scoring import risk_scoring
from app.agents.false_positive_review import false_positive_review
from app.agents.sar_drafting import sar_drafting
from app.agents.compliance_review import compliance_review
from app.agents.human_approval import human_approval


# POOR / CRITICAL_MISSING data halts here -- request more info instead of
# investigating blind. GOOD / PARTIAL data can proceed.
def route_after_data_quality(state: CaseState):
    dq = state.get("data_quality", {})
    return INVESTIGATION if dq.get("can_continue", dq.get("complete", True)) else END


# Routing after scoring:
#   tool failure                          -> human review (no SAR on bad data)
#   high risk (>= threshold)              -> draft a SAR
#   sub-threshold but an alert triggered  -> false-positive review
#   (or a possible watchlist name match)
#   sub-threshold and nothing triggered   -> auto-close (clean)
def route_after_scoring(state: CaseState):
    if state.get("errors"):
        return "human_approval"
    escalate_at = get_rules()["scoring"]["escalation_threshold"]
    if state.get("risk_score", 0) >= escalate_at:
        return "sar_drafting"

    # PARTIAL data quality means we investigated, but a human must sign off --
    # don't auto-close a case built on degraded data.
    if (state.get("data_quality") or {}).get("severity") == "PARTIAL":
        return "human_approval"

    triggered = bool(state.get("risk_factors"))
    wf = state.get("watchlist_findings", {})
    possible_match = bool(wf.get("is_match")) or any(
        (wf.get(p) or {}).get("verdict") == "POSSIBLE_MATCH_REQUIRES_REVIEW"
        for p in ("customer_screening", "recipient_screening"))
    if triggered or possible_match:
        return "false_positive_review"
    return END   # clean: nothing triggered


# After the FP review: a clear false positive auto-closes; anything else
# (incl. a sanctions/PEP name match) goes to a human.
def route_after_fp(state: CaseState):
    return END if not state.get("fp_review", {}).get("requires_human_review") else "human_approval"


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
    g.add_node("kyc_profile", kyc_profile)
    g.add_node("watchlist_screening", watchlist_screening)
    g.add_node("policy_rag", policy_rag)
    g.add_node("case_memory", case_memory)
    g.add_node("risk_scoring", risk_scoring)
    g.add_node("false_positive_review", false_positive_review)
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
                            ["sar_drafting", "false_positive_review", "human_approval", END])
    # FP review: clear false positive -> auto-close; otherwise -> human
    g.add_conditional_edges("false_positive_review", route_after_fp,
                            ["human_approval", END])
    g.add_edge("sar_drafting", "compliance_review")
    g.add_edge("compliance_review", "human_approval")
    # human decision: request_more_info loops back to investigate; else END
    g.add_conditional_edges("human_approval", route_after_approval, INVESTIGATION + [END])

    return g.compile(checkpointer=MemorySaver())
