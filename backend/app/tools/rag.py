"""
RAG layer -- the ChromaDB vector database for internal AML policies,
with two-stage retrieval for precision:

  Stage 1 (recall):    embed the query and pull the top-K candidates from
                       ChromaDB by vector similarity -- fast but coarse.
  Stage 2 (precision): a cross-encoder reranker scores each (query, policy)
                       pair together and reorders them -- slower but accurate.

Policies are embedded ONCE on first use (the 'embed-once' pattern). Both the
embedder (Ollama) and the reranker run locally, so retrieval costs nothing.
"""

import chromadb
from sentence_transformers import CrossEncoder
from app.services.llm import embed
from app.core.config import CHROMA_PATH

# Internal AML policy documents. In a real system these come from PDFs/Word
# docs run through a loader; here we hardcode a few representative sections.
POLICIES = [
    ("AML-4.2", "AML Escalation Procedure 4.2: Transactions involving unusual "
                "volume, new high-risk overseas recipients, or amounts inconsistent "
                "with the customer's declared income profile must be escalated for "
                "Level 2 compliance review and a SAR draft prepared."),
    ("AML-3.1", "Structuring Detection Policy 3.1: Multiple transfers made just "
                "below reporting thresholds within a short time window are a strong "
                "indicator of structuring and must be flagged."),
    ("KYC-2.0", "KYC Review Procedure 2.0: Declared income must be consistent with "
                "transaction volume. A significant mismatch requires enhanced due "
                "diligence before the account continues high-value activity."),
    ("WL-1.0",  "Watchlist Screening Procedure 1.0: Any sanctions or PEP match, or "
                "a strong internal blacklist match, must be reported to the "
                "compliance officer immediately."),
    ("HRC-1.0", "High-Risk Country Policy 1.0: Transfers to jurisdictions on the "
                "high-risk list require additional source-of-funds verification."),
    ("ML-5.1",  "Money Mule Policy 5.1: An account that receives a large inbound "
                "transfer and rapidly forwards the funds to multiple new recipients "
                "exhibits money-mule behaviour and must be escalated immediately."),
    ("LAY-6.1", "Layering & Dispersion Policy 6.1: Rapid dispersal of funds across "
                "many newly added recipients within a short time window indicates "
                "layering and requires enhanced scrutiny and escalation."),
]

# A small, fast cross-encoder reranker (downloads ~80MB on first use).
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_collection = None
_reranker: CrossEncoder | None = None


def get_policy_collection():
    """Return the policy collection, ingesting documents on first call only."""
    global _collection
    if _collection is not None:
        return _collection

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    coll = chroma.get_or_create_collection("aml_policies")

    # Rebuild if empty OR if the policy list changed (keeps the vector store
    # in sync with POLICIES without manually deleting chroma_db/).
    if coll.count() != len(POLICIES):
        chroma.delete_collection("aml_policies")
        coll = chroma.create_collection("aml_policies")
        ids = [p[0] for p in POLICIES]
        docs = [p[1] for p in POLICIES]
        coll.add(ids=ids, documents=docs, embeddings=embed(docs))

    _collection = coll
    return coll


def _get_reranker() -> CrossEncoder:
    """Lazily load the cross-encoder reranker on first use."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def search_policies(query: str, k: int = 5, n: int = 2) -> list[str]:
    """
    Two-stage retrieval.
      k = how many candidates to pull from the vector store (recall)
      n = how many to return after reranking (precision)
    """
    coll = get_policy_collection()

    # --- Stage 1: vector recall (fast, broad) ---
    results = coll.query(query_embeddings=embed([query]), n_results=k)
    candidates = results["documents"][0]
    if not candidates:
        return []

    # --- Stage 2: cross-encoder rerank (slow, precise) ---
    reranker = _get_reranker()
    scores = reranker.predict([(query, doc) for doc in candidates])
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)

    return [doc for doc, _ in ranked[:n]]
