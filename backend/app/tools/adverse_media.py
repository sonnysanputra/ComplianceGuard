"""
Adverse media (negative news) screening -- MOCK tool.

Watchlists only catch entities someone has formally listed. Adverse-media
screening catches entities that appear in negative news (fraud, investigations,
enforcement) before they are ever sanctioned. In production this would query a
media-intelligence provider (Dow Jones Risk & Compliance, World-Check,
LexisNexis, etc.); here we use a small in-memory mock so the whole pipeline runs
offline at no cost.

search_adverse_media(entity) -> {entity, hits[], verdict}
"""

from rapidfuzz import fuzz

# fuzzy name-match threshold (a news article rarely uses the exact legal name)
MATCH_THRESHOLD = 85

# mock negative-news database keyed by entity name
_MOCK_NEWS = {
    "Global Trade Ltd": [
        {"title": "Company linked to suspected invoice fraud network",
         "source": "Mock News Database", "risk_level": "HIGH", "date": "2026-05-01"},
    ],
    "Northern Star Holdings": [
        {"title": "Entity named in cross-border sanctions-evasion investigation",
         "source": "Mock News Database", "risk_level": "CRITICAL", "date": "2026-03-15"},
    ],
    "Ahmad Zulkifli": [
        {"title": "Politically exposed person under anti-corruption probe",
         "source": "Mock News Database", "risk_level": "HIGH", "date": "2026-02-20"},
    ],
    "Sunrise Logistics": [
        {"title": "Logistics firm fined for trade-based money laundering",
         "source": "Mock News Database", "risk_level": "MEDIUM", "date": "2025-11-08"},
    ],
}


def search_adverse_media(entity: str) -> dict:
    """Return adverse-media hits for an entity (fuzzy name match)."""
    entity = (entity or "").strip()
    if not entity:
        return {"entity": entity, "hits": [], "verdict": "NO_ADVERSE_MEDIA"}

    hits = []
    for name, articles in _MOCK_NEWS.items():
        if fuzz.token_sort_ratio(entity.lower(), name.lower()) >= MATCH_THRESHOLD:
            hits.extend(articles)

    return {
        "entity": entity,
        "hits": hits,
        "verdict": "NEGATIVE_NEWS_FOUND" if hits else "NO_ADVERSE_MEDIA",
    }
