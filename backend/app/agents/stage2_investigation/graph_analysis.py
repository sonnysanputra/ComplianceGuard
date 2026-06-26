"""
4.x Relationship Graph Agent

Builds the money-flow network around the customer and looks for the network
signatures of laundering -- fan-out (dispersion), rapid hop-by-hop forwarding
(mules), convergence on a common collector, and circular round-tripping. This is
exactly the layering/dispersion picture a single-transaction view cannot see.

Deterministic graph analysis (no LLM). Reads the transaction_edges table when
present, else derives the graph from the customer's transactions.
"""

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.core.evidence import EvidenceCollector
from app.tools.db import get_transactions, get_transaction_edges
from app.tools.graph_analysis import analyze_account


class GraphAnalysisAgent(BaseAgent):
    name = "graph_analysis"
    label = "Relationship Graph Agent"
    uses_llm = False

    def run(self, state: dict) -> dict:
        cid = state["alert"]["customer_id"]
        txns = get_transactions(cid)
        edges = get_transaction_edges()                 # best-effort; [] if no table
        g = analyze_account(cid, txns, edges)

        signals = []
        if g["fan_out_count"] >= 5:
            signals.append(f"fan-out to {g['fan_out_count']} recipients")
        if g["rapid_forwarding_detected"]:
            signals.append("rapid hop-by-hop forwarding")
        if g["common_recipient"]:
            signals.append(f"convergence on {', '.join(g['common_recipient'][:2])}")
        if g["circular_flow"]:
            signals.append("circular fund flow")
        if g["hop_count"] >= 3:
            signals.append(f"{g['hop_count']}-hop chain")

        reasoning = ("Money-flow graph: " + ("; ".join(signals) if signals
                     else "no network laundering signatures")
                     + f" (graph risk {g['graph_risk_score']}/30).")
        confidence = 0.9 if signals else 0.85

        coll = EvidenceCollector(prefix="GRAPH")
        ev_ids = []
        if g["graph_risk_score"] > 0:
            ev_ids.append(coll.add("transaction", cid, "graph_risk_score",
                                   g["graph_risk_score"],
                                   "Money-flow network: " + (", ".join(signals) or "elevated")))
        if len(g["possible_layering_path"]) >= 3:
            ev_ids.append(coll.add("transaction", cid, "layering_path",
                                   " -> ".join(g["possible_layering_path"]),
                                   "Possible layering / forwarding path"))

        g["evidence_ids"] = ev_ids
        return {
            "graph_findings": g,
            "evidence": coll.items,
            "audit_rationales": [self.trace(reasoning, confidence,
                                      evidence=signals or ["no network signatures"],
                                      output={"graph_risk_score": g["graph_risk_score"]})],
            "audit": stamp(f"{self.label}: graph risk {g['graph_risk_score']}/30"
                           + (f" ({'; '.join(signals)})" if signals else "")),
        }


graph_analysis = GraphAnalysisAgent()
