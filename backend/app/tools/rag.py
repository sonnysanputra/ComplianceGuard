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
import hashlib
import logging
from pathlib import Path

import chromadb
from sentence_transformers import CrossEncoder
from app.services.llm import embed
from app.core.config import CHROMA_PATH, POLICIES_DIR

logger = logging.getLogger(__name__)

# A small, fast cross-encoder reranker (downloads ~80MB on first use).
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
COLLECTION = "aml_policies"

_collection = None
_reranker: CrossEncoder | None = None


# ======================================================================
# Policy loading -- documents live as files in backend/policies/ so a
# compliance team can drop in their OWN .md or .pdf policies. Each .md may
# carry YAML-style frontmatter (id, title, section, category).
# ======================================================================
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    meta = {}
    body = text
    if text.lstrip().startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            body = parts[2]
    return meta, body.strip()


def _read_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            return " ".join(page.get_text() for page in doc).strip()
    except Exception as exc:
        logger.warning(f"[rag] could not read PDF {path.name}: {exc}")
        return ""


def load_policies() -> list[dict]:
    """Load every policy document from POLICIES_DIR (.md / .txt / .pdf)."""
    folder = Path(POLICIES_DIR)
    policies = []
    if not folder.exists():
        logger.warning(f"[rag] policies folder not found: {folder}")
        return policies

    for path in sorted(folder.iterdir()):
        ext = path.suffix.lower()
        if ext in (".md", ".txt"):
            meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        elif ext == ".pdf":
            meta, body = {}, _read_pdf(path)
        else:
            continue
        if not body:
            continue
        policies.append({
            "id": meta.get("id") or path.stem.upper(),
            "title": meta.get("title") or path.stem.replace("_", " ").title(),
            "section": meta.get("section", ""),
            "category": meta.get("category", "General"),
            "text": body,
        })
    return policies


def _policies_hash(policies: list[dict]) -> str:
    h = hashlib.sha256()
    for p in policies:
        h.update((p["id"] + p["text"]).encode("utf-8"))
    return h.hexdigest()[:16]


def get_policy_collection():
    """Return the policy collection. Loads documents from files and rebuilds the
    vector store whenever the policy set CHANGES (new/edited/removed files),
    detected via a content hash -- so uploading a new policy re-indexes it."""
    global _collection
    if _collection is not None:
        return _collection

    policies = load_policies()
    phash = _policies_hash(policies)

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    coll = chroma.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine", "policy_hash": phash})

    # rebuild if the document set changed (count or content hash differs)
    if policies and (coll.count() != len(policies)
                     or (coll.metadata or {}).get("policy_hash") != phash):
        try:
            chroma.delete_collection(COLLECTION)
        except Exception:
            pass
        coll = chroma.create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine", "policy_hash": phash})
        coll.add(
            ids=[p["id"] for p in policies],
            documents=[p["text"] for p in policies],
            embeddings=embed([p["text"] for p in policies]),
            metadatas=[{"id": p["id"], "title": p["title"],
                        "section": p["section"], "category": p["category"]}
                       for p in policies],
        )
        logger.info(f"[rag] indexed {len(policies)} policy documents")

    _collection = coll
    return coll


def reset_policy_collection():
    """Drop the cached collection so the next access re-loads the policy files
    and re-indexes them. Call this after adding/editing a policy at runtime."""
    global _collection
    _collection = None
    return get_policy_collection()


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
