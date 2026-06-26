"""
4.x Adverse Media Screening Agent (hybrid: deterministic fetch + grounded LLM judgment)

Screens BOTH parties (customer and recipient) for negative news -- fraud,
investigations, enforcement -- which a sanctions/PEP watchlist does not capture.

  1. DETERMINISTIC: the tool fetches real headlines from the live web (Google News).
  2. LLM JUDGMENT:  Qwen reviews ONLY those fetched headlines to (a) disambiguate --
     is the article about THIS entity or a different same-name party? -- and
     (b) grade the AML severity. The prompt is strict and grounded (use only the
     headlines, never invent), so the model adds judgment without hallucinating.

Falls back to the deterministic keyword severity if the LLM is unavailable, so the
screen still works offline.
"""

_RISK_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_VALID_LEVELS = set(_RISK_ORDER)

from app.agents.base import BaseAgent, CONFIDENCE_RUBRIC
from app.core.state import stamp
from app.core.evidence import EvidenceCollector
from app.tools.db import get_customer
from app.tools.adverse_media import search_adverse_media

SYSTEM_PROMPT = """You are an AML adverse-media analyst. You are given an ENTITY NAME and \
a numbered list of REAL news headlines that mention a similar name. For EACH headline, \
using ONLY the headline text provided, decide two things:

1. RELEVANCE (disambiguation): Is the headline plausibly about THIS entity, or about a \
different person/company that merely shares a similar name? If it is ambiguous, or clearly \
a different party, mark it NOT relevant. Do not assume relevance.

2. AML RISK LEVEL of the negative news (only if relevant):
   - CRITICAL : sanctions, terrorism financing, money laundering
   - HIGH     : fraud, bribery, corruption, embezzlement, Ponzi/investment scam, indictment, conviction
   - MEDIUM   : ongoing investigation, regulatory probe, lawsuit, fine/penalty, allegations
   - LOW      : minor, dated, civil-only, or loosely AML-related
   - NONE     : the headline describes no financial-crime wrongdoing

STRICT RULES (to avoid hallucination)
- Use ONLY the headlines given. NEVER invent facts, outcomes, names, amounts, or details not in the text.
- Do not infer guilt beyond the wording: "alleged", "probe", "investigation" => MEDIUM, not HIGH.
- A positive, neutral, or non-financial-crime headline => relevant=false (or risk_level NONE).
- When in doubt about the entity's identity, mark relevant=false (be conservative)."""


class AdverseMediaScreeningAgent(BaseAgent):
    name = "adverse_media_screening"
    label = "Adverse Media Screening Agent"
    prompt_version = "adverse_media_v1"
    uses_llm = True                       # the LLM judges the fetched headlines

    def run(self, state: dict) -> dict:
        alert = state["alert"]
        cust = get_customer(alert["customer_id"])
        parties = {
            "customer": cust["name"] if cust else alert["customer_id"],
            "recipient": alert.get("recipient", ""),
        }

        # ---- 1. deterministic fetch (real web headlines / curated fallback) ----
        screenings, raw_hits = {}, []
        for role, name in parties.items():
            res = search_adverse_media(name)
            screenings[role] = res
            for h in res["hits"]:
                raw_hits.append({"party": role, "name": name, **h})

        # ---- 2. grounded LLM review of the fetched headlines ----
        hits, llm_used, confidence = self._review(raw_hits)

        highest = "NONE"
        coll = EvidenceCollector(prefix="AM")
        ev_ids = []
        for h in hits:
            if _RISK_ORDER.get(h["risk_level"], 0) > _RISK_ORDER.get(highest, 0):
                highest = h["risk_level"]
            ev_ids.append(coll.add("adverse_media", h["name"], "negative_news",
                                   h["risk_level"], h["title"]))

        negative = bool(hits)
        verdict = "NEGATIVE_NEWS_FOUND" if negative else "NO_ADVERSE_MEDIA"
        dropped = len(raw_hits) - len(hits)
        required_action = ("Manual review required -- adverse media found."
                           if negative else "No adverse media; no action required.")
        lookup_source = next((s["source"] for s in screenings.values() if s.get("hits")), "none")

        if negative:
            titles = "; ".join(h["title"] for h in hits[:2])
            reasoning = (f"Adverse media: {len(hits)} relevant negative-news hit(s) "
                         f"(highest {highest}): {titles}."
                         + (f" {dropped} same-name article(s) ruled out." if dropped else ""))
        else:
            reasoning = (f"Screened {len(parties)} parties for negative news. "
                         + ("All fetched articles ruled out as different same-name parties."
                            if raw_hits else "No adverse media found."))

        return {
            "adverse_media_findings": {
                "customer_screening": screenings["customer"],
                "recipient_screening": screenings["recipient"],
                "verdict": verdict,
                "negative_news": negative,
                "highest_risk_level": highest,
                "hit_count": len(hits),
                "articles_ruled_out": dropped,
                "all_hits": hits,
                "lookup_source": lookup_source,
                "reviewed_by_llm": llm_used,
                "required_action": required_action,
                "evidence_ids": ev_ids,
            },
            "evidence": coll.items,
            "audit_rationales": [self.trace(
                reasoning, confidence,
                evidence=[f"{h['party']} '{h['name']}': {h['title']} ({h['risk_level']})" for h in hits],
                output={"verdict": verdict, "hits": len(hits), "reviewed_by_llm": llm_used})],
            "audit": stamp(f"{self.label} screened {len(parties)} parties -> {verdict}"),
        }

    def _review(self, raw_hits: list[dict]) -> tuple[list[dict], bool, float]:
        """Have Qwen judge relevance + severity of the fetched headlines. Returns
        (kept_hits, llm_used, confidence). Falls back to the deterministic hits."""
        if not raw_hits:
            return [], False, 0.85

        listing = "\n".join(f"{i}. entity=\"{h['name']}\" | headline: {h['title']}"
                            for i, h in enumerate(raw_hits))
        analysis = self.think(
            system=SYSTEM_PROMPT,
            prompt=(
                "Review these headlines (one per line, indexed):\n"
                f"{listing}\n\n"
                "Return ONLY this JSON:\n"
                "{\n"
                '  "reviews": [{"index": <int>, "relevant": <true|false>, '
                '"risk_level": "CRITICAL|HIGH|MEDIUM|LOW|NONE"}],\n'
                '  "confidence": <0-100>\n'
                "}\n\n"
                f"{CONFIDENCE_RUBRIC}"
            ),
        )
        reviews = analysis.get("reviews")
        if not isinstance(reviews, list) or not reviews:
            return raw_hits, False, 0.85           # offline / parse failure -> deterministic

        by_index = {r.get("index"): r for r in reviews if isinstance(r, dict)}
        kept = []
        for i, h in enumerate(raw_hits):
            r = by_index.get(i)
            if r is None:                          # unreviewed -> keep deterministic
                kept.append(h); continue
            if not r.get("relevant", True):        # disambiguation: drop same-name noise
                continue
            level = str(r.get("risk_level", "")).upper()
            if level in _VALID_LEVELS and level != "NONE":
                h = {**h, "risk_level": level}
            elif level == "NONE":
                continue
            kept.append(h)
        confidence = float(analysis.get("confidence", 85)) / 100.0
        return kept, True, confidence


adverse_media_screening = AdverseMediaScreeningAgent()
