"""
4.4 Watchlist Screening Agent (dual-party, multi-list)

Screens BOTH parties -- the customer AND the recipient -- against every watchlist
entry (sanctions / PEP / internal blacklist), scoring each party against each
entry. Returns all matches above a review threshold, the best per list type, and
an aggregate verdict. Pure deterministic matching (rapidfuzz) -- the correct tool
for name screening; an LLM would only add noise here.
"""

from rapidfuzz import fuzz

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.tools.db import get_watchlist, get_customer, HIGH_RISK_COUNTRIES

MATCH_THRESHOLD = 80     # >= this is treated as a hit
REVIEW_THRESHOLD = 70    # >= this is surfaced for manual review


class WatchlistScreeningAgent(BaseAgent):
    name = "watchlist_screening"
    label = "Watchlist Screening Agent"

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cust = get_customer(alert["customer_id"])

        # screen both parties
        parties = {
            "customer": cust["name"] if cust else alert["customer_id"],
            "recipient": alert.get("recipient", ""),
        }
        watchlist = get_watchlist()

        matches = []
        for role, name in parties.items():
            for entry in watchlist:
                score = fuzz.token_sort_ratio(name.lower(), entry["entity_name"].lower())
                if score >= REVIEW_THRESHOLD:
                    matches.append({
                        "party": role, "name": name,
                        "matched_entity": entry["entity_name"],
                        "list_type": entry["list_type"],
                        "risk_level": entry.get("risk_level"),
                        "score": round(score, 1),
                    })
        matches.sort(key=lambda m: m["score"], reverse=True)

        best = matches[0] if matches else None
        is_match = any(m["score"] >= MATCH_THRESHOLD for m in matches)

        # best score per list type (sanctions / PEP / blacklist)
        per_list = {}
        for m in matches:
            lt = m["list_type"]
            per_list[lt] = max(per_list.get(lt, 0), m["score"])

        high_risk_country = alert.get("country", "") in HIGH_RISK_COUNTRIES

        verdict = ("Confirmed match - escalate" if is_match else
                   "Possible match - manual review" if matches else
                   "No watchlist match")

        if best:
            reasoning = (f"Screened {len(parties)} parties against {len(watchlist)} entries. "
                         f"Best: {best['party']} '{best['name']}' ~ '{best['matched_entity']}' "
                         f"({best['score']:.0f}%, {best['list_type']}). Verdict: {verdict}.")
            confidence = round(best["score"] / 100.0, 2)
        else:
            reasoning = (f"Screened {len(parties)} parties against {len(watchlist)} entries. "
                         f"No matches above {REVIEW_THRESHOLD}%. Clear.")
            confidence = 0.9   # confident there is no hit

        return {
            "watchlist_findings": {
                "best_match": best["matched_entity"] if best else None,
                "match_score": best["score"] if best else 0,
                "list_type": best["list_type"] if best else None,
                "is_match": is_match,
                "high_risk_country": high_risk_country,
                "all_matches": matches,
                "per_list_best": per_list,
                "screened_parties": list(parties.keys()),
                "verdict": verdict,
            },
            "cot_traces": [self.trace(reasoning, confidence,
                                      output={"is_match": is_match, "matches": len(matches)})],
            "audit": stamp(f"{self.label} screened {len(parties)} parties -> {verdict}"),
        }


watchlist_screening = WatchlistScreeningAgent()
