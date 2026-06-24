"""
RAG layer -- the ChromaDB vector database for internal AML policies,
with two-stage retrieval for precision:

  Stage 1 (recall):    embed the query and pull the top-K candidates from
                       ChromaDB by vector similarity -- fast but coarse.
  Stage 2 (precision): a cross-encoder reranker scores each (query, policy)
                       pair together and reorders them -- slower but accurate.

search_policies returns STRUCTURED CITATIONS (id, title, section, content, and
both retrieval + rerank scores) so every policy used is explainable and auditable.

Policies are embedded ONCE on first use (the 'embed-once' pattern). Both the
embedder (Ollama) and the reranker run locally, so retrieval costs nothing.
"""

import math

import chromadb
from sentence_transformers import CrossEncoder
from app.services.llm import embed
from app.core.config import CHROMA_PATH

# Internal AML policy documents WITH metadata (id / title / section / category)
# so retrieval can return proper citations. In production these come from PDFs
# run through a loader; here we hardcode a few representative sections.
POLICIES = [
    {"id": "AML-4.2", "title": "AML Escalation Procedure", "section": "4.2",
     "category": "Escalation",
     "text": "Transactions involving unusual volume, new high-risk overseas "
             "recipients, or amounts inconsistent with the customer's declared "
             "income profile must be escalated for Level 2 compliance review and "
             "a SAR draft prepared."},
    {"id": "AML-3.1", "title": "Structuring Detection Policy", "section": "3.1",
     "category": "Detection",
     "text": "Multiple transfers made just below reporting thresholds within a "
             "short time window are a strong indicator of structuring and must be flagged."},
    {"id": "KYC-2.0", "title": "KYC Review Procedure", "section": "2.0",
     "category": "KYC",
     "text": "Declared income must be consistent with transaction volume. A "
             "significant mismatch requires enhanced due diligence before the "
             "account continues high-value activity."},
    {"id": "WL-1.0", "title": "Watchlist Screening Procedure", "section": "1.0",
     "category": "Screening",
     "text": "Any sanctions or PEP match, or a strong internal blacklist match, "
             "must be reported to the compliance officer immediately."},
    {"id": "HRC-1.0", "title": "High-Risk Country Policy", "section": "1.0",
     "category": "Jurisdiction",
     "text": "Transfers to jurisdictions on the high-risk list require additional "
             "source-of-funds verification."},
    {"id": "ML-5.1", "title": "Money Mule Policy", "section": "5.1",
     "category": "Detection",
     "text": "An account that receives a large inbound transfer and rapidly "
             "forwards the funds to multiple new recipients exhibits money-mule "
             "behaviour and must be escalated immediately."},
    {"id": "LAY-6.1", "title": "Layering & Dispersion Policy", "section": "6.1",
     "category": "Detection",
     "text": "Rapid dispersal of funds across many newly added recipients within "
             "a short time window indicates layering and requires enhanced "
             "scrutiny and escalation."},
]

# A small, fast cross-encoder reranker (downloads ~80MB on first use).
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# Bump the collection name when the policy schema changes -> forces a clean rebuild.
COLLECTION = "aml_policies_v2"

_collection = None
_reranker: CrossEncoder | None = None


def get_policy_collection():
    """Return the policy collection, ingesting documents (with metadata) on first
    call only. Uses cosine distance so retrieval scores are interpretable."""
    global _collection
    if _collection is not None:
        return _collection

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    coll = chroma.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"})

    if coll.count() != len(POLICIES):
        chroma.delete_collection(COLLECTION)
        coll = chroma.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        coll.add(
            ids=[p["id"] for p in POLICIES],
            documents=[p["text"] for p in POLICIES],
            embeddings=embed([p["text"] for p in POLICIES]),
            metadatas=[{"id": p["id"], "title": p["title"],
                        "section": p["section"], "category": p["category"]}
                       for p in POLICIES],
        )

    _collection = coll
    return coll


def _get_reranker() -> CrossEncoder:
    """Lazily load the cross-encoder reranker on first use."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def search_policies(query: str, k: int = 5, n: int = 2) -> list[dict]:
    """
    Two-stage retrieval returning structured, scored citations.
      k = candidates pulled from the vector store (recall)
      n = citations returned after reranking (precision)
    Each result: {policy_id, title, section, category, content,
                  retrieval_score, rerank_score}
    """
    coll = get_policy_collection()

    # --- Stage 1: vector recall (fast, broad) ---
    res = coll.query(
        query_embeddings=embed([query]), n_results=k,
        include=["documents", "metadatas", "distances"])
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    if not docs:
        return []

    # --- Stage 2: cross-encoder rerank (slow, precise) ---
    reranker = _get_reranker()
    rerank_logits = reranker.predict([(query, d) for d in docs])

    citations = []
    for doc, meta, dist, logit in zip(docs, metas, dists, rerank_logits):
        citations.append({
            "policy_id": meta.get("id"),
            "title": meta.get("title"),
            "section": meta.get("section"),
            "category": meta.get("category"),
            "content": doc,
            "retrieval_score": round(max(0.0, 1 - dist), 3),         # cosine -> similarity
            "rerank_score": round(1 / (1 + math.exp(-float(logit))), 3),  # sigmoid -> 0..1
        })

    citations.sort(key=lambda c: c["rerank_score"], reverse=True)
    return citations[:n]
