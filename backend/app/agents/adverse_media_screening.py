"""
4.x Adverse Media Screening Agent

Screens BOTH parties (customer and recipient) for negative news -- fraud,
investigations, enforcement actions -- via the adverse-media tool. Negative news
is a real AML risk signal that a sanctions/PEP watchlist does not capture, so a
hit feeds the risk score (the rule engine adds points) and always warrants human
attention.

Pure deterministic screening (no LLM): the mock tool does fuzzy name matching.
"""

_RISK_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

from app.agents.base import BaseAgent
from app.core.state import stamp
from app.core.evidence import EvidenceCollector
from app.tools.db import get_customer
from app.tools.adverse_media import search_adverse_media


class AdverseMediaScreeningAgent(BaseAgent):
    name = "adverse_media_screening"
    label = "Adverse Media Screening Agent"

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cust = get_customer(alert["customer_id"])
        parties = {
            "customer": cust["name"] if cust else alert["customer_id"],
            "recipient": alert.get("recipient", ""),
        }

        coll = EvidenceCollector(prefix="AM")
        screenings, all_hits, ev_ids = {}, [], []
        highest = "NONE"
        for role, name in parties.items():
            res = search_adverse_media(name)
            screenings[role] = res
            for h in res["hits"]:
                all_hits.append({"party": role, "name": name, **h})
                if _RISK_ORDER.get(h["risk_level"], 0) > _RISK_ORDER.get(highest, 0):
                    highest = h["risk_level"]
                ev_ids.append(coll.add("adverse_media", name, "negative_news",
                                       h["risk_level"], h["title"]))

        negative = bool(all_hits)
        verdict = "NEGATIVE_NEWS_FOUND" if negative else "NO_ADVERSE_MEDIA"
        required_action = ("Manual review required -- adverse media found."
                           if negative else "No adverse media; no action required.")

        if negative:
            titles = "; ".join(h["title"] for h in all_hits[:2])
            reasoning = (f"Adverse media screening found {len(all_hits)} negative-news hit(s) "
                         f"(highest {highest}): {titles}.")
            confidence = 0.9
        else:
            reasoning = (f"Screened {len(parties)} parties for negative news. "
                         f"No adverse media found.")
            confidence = 0.85

        return {
            "adverse_media_findings": {
                "customer_screening": screenings["customer"],
                "recipient_screening": screenings["recipient"],
                "verdict": verdict,
                "negative_news": negative,
                "highest_risk_level": highest,
                "hit_count": len(all_hits),
                "all_hits": all_hits,
                "required_action": required_action,
                "evidence_ids": ev_ids,
            },
            "evidence": coll.items,
            "audit_rationales": [self.trace(
                reasoning, confidence,
                evidence=[f"{h['party']} '{h['name']}': {h['title']} ({h['risk_level']})"
                          for h in all_hits],
                output={"verdict": verdict, "hits": len(all_hits)})],
            "audit": stamp(f"{self.label} screened {len(parties)} parties -> {verdict}"),
        }


adverse_media_screening = AdverseMediaScreeningAgent()
