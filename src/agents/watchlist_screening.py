"""
4.4 Watchlist Screening Agent

Fuzzy-matches the recipient against the watchlist (sanctions / PEP / blacklist)
and checks for high-risk jurisdictions. Pure Python (rapidfuzz) -- confidence is
the match strength itself.
"""

from rapidfuzz import fuzz

from .base import BaseAgent
from ..state import stamp
from ..tools.db import get_watchlist, HIGH_RISK_COUNTRIES


class WatchlistScreeningAgent(BaseAgent):
    name = "watchlist_screening"
    label = "Watchlist Screening Agent"

    def run(self, state: dict) -> dict:
        recipient = state["alert"].get("recipient", "")
        best_name, best_score, best_type = None, 0, None
        for entry in get_watchlist():
            score = fuzz.token_sort_ratio(recipient.lower(), entry["entity_name"].lower())
            if score > best_score:
                best_name, best_score, best_type = entry["entity_name"], score, entry["list_type"]

        country = state["alert"].get("country", "")
        is_match = best_score >= 80
        high_risk_country = country in HIGH_RISK_COUNTRIES

        reasoning = (
            f"Best watchlist match: '{best_name}' at {best_score:.0f}% "
            f"({best_type}). {'Treated as a match.' if is_match else 'Below match threshold.'} "
            f"High-risk country: {'yes' if high_risk_country else 'no'} ({country})."
        )
        confidence = round(best_score / 100.0, 2)

        return {
            "watchlist_findings": {
                "best_match": best_name,
                "match_score": round(best_score, 1),
                "list_type": best_type,
                "is_match": is_match,
                "high_risk_country": high_risk_country,
            },
            "cot_traces": [self.trace(reasoning, confidence, output={"is_match": is_match})],
            "audit": stamp(f"{self.label} best match {best_score:.0f}% ({best_name})"),
        }


watchlist_screening = WatchlistScreeningAgent()
