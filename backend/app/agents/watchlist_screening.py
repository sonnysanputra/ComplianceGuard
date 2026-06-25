"""
4.4 Watchlist Screening Agent (dual-party, multi-list)

Screens BOTH parties -- the customer AND the recipient -- against every active
watchlist entity across all lists (UN sanctions, PEP, internal blacklist, adverse
media, scam/mule accounts, high-risk entities). Returns a per-party screening
result with a verdict and a required action.

Pure deterministic name matching (rapidfuzz) -- the correct tool here; an LLM
would only add noise. A fuzzy hit always requires HUMAN verification before the
case is cleared (a name match is never auto-confirmed).
"""

from rapidfuzz import fuzz

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.rules.rule_engine import get_rules
from app.rules.country_risk import high_risk_countries
from app.tools.db import get_watchlist, get_customer


class WatchlistScreeningAgent(BaseAgent):
    name = "watchlist_screening"
    label = "Watchlist Screening Agent"

    def run(self, state: dict) -> dict:
        wl_rules = get_rules()["watchlist"]
        match_threshold = wl_rules["match_threshold"]
        review_threshold = wl_rules["review_threshold"]

        alert = state["alert"]
        cust = get_customer(alert["customer_id"])
        entities = get_watchlist()

        parties = {
            "customer": cust["name"] if cust else alert["customer_id"],
            "recipient": alert.get("recipient", ""),
        }

        all_matches = []
        screenings = {}
        for role, name in parties.items():
            best = None
            for e in entities:
                score = fuzz.token_sort_ratio(name.lower(), e["entity_name"].lower())
                if score >= review_threshold:
                    m = {"party": role, "searched_name": name,
                         "matched_entity": e["entity_name"],
                         "matched_entity_id": e.get("id"),
                         "list_type": e.get("list_type"),
                         "risk_level": e.get("risk_level"),
                         "score": round(score, 1),
                         "match_type": "exact" if score >= 99 else "fuzzy"}
                    all_matches.append(m)
                    if best is None or score > best["score"]:
                        best = m
            if best:
                screenings[role] = {
                    "searched_name": name, "best_match": best["matched_entity"],
                    "list_type": best["list_type"], "match_score": best["score"],
                    "verdict": "POSSIBLE_MATCH_REQUIRES_REVIEW"}
            else:
                screenings[role] = {
                    "searched_name": name, "best_match": None, "list_type": None,
                    "match_score": 0, "verdict": "NO_MATCH"}

        overall_best = max(all_matches, key=lambda m: m["score"]) if all_matches else None
        is_match = any(m["score"] >= match_threshold for m in all_matches)
        needs_review = any(s["verdict"] == "POSSIBLE_MATCH_REQUIRES_REVIEW"
                           for s in screenings.values())
        required_action = ("Manual verification required before clearing the case."
                           if needs_review else "No watchlist action required.")
        high_risk_country = alert.get("country", "") in high_risk_countries()
        verdict = "Possible match - manual review" if needs_review else "No watchlist match"

        if overall_best:
            reasoning = (f"Screened {len(parties)} parties against {len(entities)} active "
                         f"list entities. Best: {overall_best['party']} "
                         f"'{overall_best['searched_name']}' ~ '{overall_best['matched_entity']}' "
                         f"({overall_best['score']:.0f}%, {overall_best['list_type']}). "
                         f"Requires human verification.")
            confidence = round(overall_best["score"] / 100.0, 2)
        else:
            reasoning = (f"Screened {len(parties)} parties against {len(entities)} active "
                         f"entities. No matches above {review_threshold}%. Clear.")
            confidence = 0.9

        return {
            "watchlist_findings": {
                "customer_screening": screenings["customer"],
                "recipient_screening": screenings["recipient"],
                "required_action": required_action,
                # --- compat fields consumed by the rule engine / scoring / display ---
                "is_match": is_match,
                "best_match": overall_best["matched_entity"] if overall_best else None,
                "match_score": overall_best["score"] if overall_best else 0,
                "list_type": overall_best["list_type"] if overall_best else None,
                "verdict": verdict,
                "high_risk_country": high_risk_country,
                "all_matches": all_matches,
                "screened_parties": list(parties.keys()),
            },
            "cot_traces": [self.trace(reasoning, confidence,
                                      output={"is_match": is_match, "matches": len(all_matches)})],
            "audit": stamp(f"{self.label} screened {len(parties)} parties -> {verdict}"),
        }


watchlist_screening = WatchlistScreeningAgent()
