"""
4.5 Policy RAG Agent

Retrieves the most relevant internal AML policies using two-stage RAG
(vector recall -> cross-encoder rerank). No LLM here -- retrieval only.
"""

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.tools.rag import search_policies


class PolicyRAGAgent(BaseAgent):
    name = "policy_rag"
    label = "Policy RAG Agent"

    def run(self, state: dict) -> dict:
        query = state["alert"]["reason"]
        policies = search_policies(query, k=5, n=2)        # recall 5, rerank to 2

        cites = ", ".join(f"{p['policy_id']} ({p['rerank_score']:.0%})" for p in policies)
        reasoning = (
            f"Searched the policy base for '{query}'. Retrieved and reranked the top "
            f"{len(policies)} citations: {cites or 'none'}."
        )
        confidence = 0.9 if policies else 0.3

        return {
            "retrieved_policies": policies,
            "cot_traces": [self.trace(reasoning, confidence,
                                      output={"citations": [p["policy_id"] for p in policies]})],
            "audit": stamp(f"{self.label} retrieved {len(policies)} citations: {cites or 'none'}"),
        }


policy_rag = PolicyRAGAgent()
