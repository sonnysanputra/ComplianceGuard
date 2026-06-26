"""
Adverse media (negative news) screening.

Watchlists only catch entities someone has formally listed. Adverse-media
screening catches entities that surface in negative news (fraud, investigations,
enforcement) before they are ever sanctioned.

This searches the live web via the Google News RSS feed -- free, no API key -- for
the entity name in an AML-risk context. It is best-effort: a short timeout + a
curated fallback list of known adverse entities, so screening still works (and
tests stay deterministic) when the web is unreachable. Set ADVERSE_MEDIA_LIVE=0
to disable the web call entirely.

In production the web call would be swapped for a licensed feed (Dow Jones Risk &
Compliance, World-Check, LexisNexis) -- same interface, richer + disambiguated data.

search_adverse_media(entity) -> {entity, hits[], verdict, source}
"""

import os
import re
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 85                       # fuzzy threshold for the curated fallback
_LIVE = os.getenv("ADVERSE_MEDIA_LIVE", "1") != "0"
GNEWS_URL = "https://news.google.com/rss/search"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 CompliGuard-AML/1.0"

# the AML-risk context that turns "a news mention" into "adverse media"
_AML_TERMS = ("fraud OR laundering OR sanctions OR bribery OR corruption "
              "OR investigation OR embezzlement OR scam OR ponzi OR indictment")

# keyword -> risk level (scanned against the article headline)
_RISK_TERMS = {
    "CRITICAL": ("sanction", "terror", "money laundering", "laundering", "indict"),
    "HIGH": ("fraud", "bribery", "corruption", "embezzle", "ponzi", "scam"),
    "MEDIUM": ("investigation", "probe", "lawsuit", "fine", "penalt", "alleged", "charged"),
}

# curated fallback: known adverse entities (used when the web call returns nothing
# or is unavailable). Keeps the demo + offline tests deterministic.
_CURATED = {
    "Global Trade Ltd": [
        {"title": "Company linked to suspected invoice fraud network",
         "source": "Curated AML list", "url": None, "risk_level": "HIGH", "date": "2026-05-01"},
    ],
    "Northern Star Holdings": [
        {"title": "Entity named in cross-border sanctions-evasion investigation",
         "source": "Curated AML list", "url": None, "risk_level": "CRITICAL", "date": "2026-03-15"},
    ],
    "Ahmad Zulkifli": [
        {"title": "Politically exposed person under anti-corruption probe",
         "source": "Curated AML list", "url": None, "risk_level": "HIGH", "date": "2026-02-20"},
    ],
}

_cache: dict[str, list[dict]] = {}         # per-process cache (entity -> hits)


def _risk_from_title(title: str) -> str:
    t = title.lower()
    for level, terms in _RISK_TERMS.items():
        if any(term in t for term in terms):
            return level
    return "MEDIUM"


def _fetch_news(entity: str, max_records: int = 5, timeout: int = 8) -> list[dict]:
    """Query Google News RSS for negative news about `entity`. Returns hits or []
    on any error. Cached per process so repeat lookups don't re-hit the feed."""
    if entity in _cache:
        return _cache[entity]
    q = f'"{entity}" ({_AML_TERMS})'
    url = f"{GNEWS_URL}?" + urllib.parse.urlencode({
        "q": q, "hl": "en-US", "gl": "US", "ceid": "US:en",
    })
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except Exception as exc:
        logger.warning(f"[adverse_media] live lookup failed for '{entity}': {exc}")
        return []

    hits, seen = [], set()
    for item in root.iter("item"):
        raw = (item.findtext("title") or "").strip()
        if not raw:
            continue
        # Google News titles read "Headline - Publisher" -> split the source off
        title, _, pub = raw.rpartition(" - ")
        title = title or raw
        src_el = item.find("source")
        source = (src_el.text if src_el is not None and src_el.text else pub) or "news"
        if title in seen:
            continue
        seen.add(title)
        pubdate = (item.findtext("pubDate") or "")
        m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", pubdate)
        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else pubdate[:16]
        hits.append({
            "title": title, "source": source, "url": item.findtext("link"),
            "risk_level": _risk_from_title(title), "date": date,
        })
        if len(hits) >= max_records:
            break
    _cache[entity] = hits
    return hits


def _curated(entity: str) -> list[dict]:
    for name, articles in _CURATED.items():
        if fuzz.token_sort_ratio(entity.lower(), name.lower()) >= MATCH_THRESHOLD:
            return articles
    return []


def search_adverse_media(entity: str, use_live: bool | None = None) -> dict:
    """Return adverse-media hits for an entity: live web search first, curated
    fallback second."""
    entity = (entity or "").strip()
    if not entity:
        return {"entity": entity, "hits": [], "verdict": "NO_ADVERSE_MEDIA", "source": "none"}

    live = _LIVE if use_live is None else use_live
    hits, source = ([], "none")
    if live:
        hits = _fetch_news(entity)
        if hits:
            source = "Google News (live web)"
    if not hits:                                   # nothing live, or offline -> curated
        hits = _curated(entity)
        if hits:
            source = "curated AML list"

    return {
        "entity": entity, "hits": hits, "source": source,
        "verdict": "NEGATIVE_NEWS_FOUND" if hits else "NO_ADVERSE_MEDIA",
    }
