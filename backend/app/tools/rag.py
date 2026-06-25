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


ALLOWED_EXTS = {".md", ".txt", ".pdf"}


def _policy_from_path(path: Path) -> dict | None:
    """Parse a single policy file into a structured policy dict (or None)."""
    ext = path.suffix.lower()
    if ext in (".md", ".txt"):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    elif ext == ".pdf":
        meta, body = {}, _read_pdf(path)
    else:
        return None
    if not body:
        return None
    return {
        "id": meta.get("id") or path.stem.upper(),
        "title": meta.get("title") or path.stem.replace("_", " ").title(),
        "section": meta.get("section", ""),
        "category": meta.get("category", "General"),
        "jurisdiction": meta.get("jurisdiction", "General"),
        "source": meta.get("source", ""),
        "text": body,
        "filename": path.name,
    }


def load_policies() -> list[dict]:
    """Load every policy document from POLICIES_DIR (.md / .txt / .pdf)."""
    folder = Path(POLICIES_DIR)
    if not folder.exists():
        logger.warning(f"[rag] policies folder not found: {folder}")
        return []
    return [p for path in sorted(folder.iterdir())
            if (p := _policy_from_path(path)) is not None]


def get_policy(policy_id: str) -> dict | None:
    """Return the full policy (incl. text) for a policy_id, or None."""
    for p in load_policies():
        if p["id"] == policy_id:
            return p
    return None


def _file_for_policy(policy_id: str) -> Path | None:
    folder = Path(POLICIES_DIR)
    if not folder.exists():
        return None
    for path in sorted(folder.iterdir()):
        pol = _policy_from_path(path)
        if pol and pol["id"] == policy_id:
            return path
    return None


def save_uploaded_policy(filename: str, data: bytes) -> dict:
    """Save an uploaded policy file into POLICIES_DIR and re-index. Returns the
    parsed policy. Raises ValueError for unsupported types or empty content."""
    safe = Path(filename).name                       # strip any path components
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTS)}")
    folder = Path(POLICIES_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / safe
    dest.write_bytes(data)
    policy = _policy_from_path(dest)
    if policy is None:
        dest.unlink(missing_ok=True)
        raise ValueError("File had no readable policy content.")
    reset_policy_collection()                        # re-index so it's searchable now
    return policy


def delete_policy(policy_id: str) -> bool:
    """Delete the file backing a policy and re-index. True if it existed."""
    path = _file_for_policy(policy_id)
    if path is None:
        return False
    path.unlink(missing_ok=True)
    reset_policy_collection()
    return True


# ======================================================================
# Chunking -- short demo policies index fine whole, but real-world policy
# PDFs are long, so we split them into section-level chunks. We chunk by
# markdown heading first (so a citation maps to an actual section), and fall
# back to a sliding window for any section that is still too long.
# ======================================================================
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_MIN_CHUNK_CHARS = 20


def chunk_policy(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Sliding-window chunker with overlap (fallback for long unstructured text)."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []
    overlap = min(overlap, chunk_size - 1)        # guard against a non-advancing window
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def chunk_by_headings(text: str) -> list[tuple[str | None, str]]:
    """Split markdown into (section_title, section_text) by its headings.
    Text before the first heading is kept as a leading (None-titled) chunk."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [(None, text.strip())] if text.strip() else []

    sections = []
    if matches[0].start() > 0:
        pre = text[:matches[0].start()].strip()
        if pre:
            sections.append((None, pre))
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        chunk_text = f"{m.group(0).strip()}\n{body}".strip()   # keep heading for context
        sections.append((title, chunk_text))
    return sections


def chunk_policy_doc(policy: dict, chunk_size: int = 800, overlap: int = 120) -> list[dict]:
    """Split one policy into section-level chunks with per-chunk metadata.
    Each chunk: chunk_id, policy_id, title, section, category, jurisdiction, source, text."""
    chunks, idx = [], 0
    for sec_title, sec_text in chunk_by_headings(policy["text"]):
        section_label = sec_title or policy.get("section") or ""
        for piece in chunk_policy(sec_text, chunk_size, overlap):
            if len(piece.strip()) < _MIN_CHUNK_CHARS:
                continue
            idx += 1
            chunks.append({
                "chunk_id": f"{policy['id']}-{idx:03d}",
                "policy_id": policy["id"],
                "title": policy["title"],
                "section": section_label,
                "category": policy["category"],
                "jurisdiction": policy["jurisdiction"],
                "source": policy["source"],
                "text": piece.strip(),
            })
    if not chunks:   # never index an empty policy as nothing
        chunks.append({"chunk_id": f"{policy['id']}-001", "policy_id": policy["id"],
                       "title": policy["title"], "section": policy.get("section", ""),
                       "category": policy["category"], "jurisdiction": policy["jurisdiction"],
                       "source": policy["source"], "text": policy["text"]})
    return chunks


def _chunks_hash(chunks: list[dict]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update((c["chunk_id"] + c["text"]).encode("utf-8"))
    return h.hexdigest()[:16]


def get_policy_collection():
    """Return the policy collection. Loads documents from files and rebuilds the
    vector store whenever the policy set CHANGES (new/edited/removed files),
    detected via a content hash -- so uploading a new policy re-indexes it."""
    global _collection
    if _collection is not None:
        return _collection

    policies = load_policies()
    chunks = [c for p in policies for c in chunk_policy_doc(p)]   # section-level chunks
    phash = _chunks_hash(chunks)

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    coll = chroma.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine", "policy_hash": phash})

    # rebuild if the chunk set changed (count or content hash differs)
    if chunks and (coll.count() != len(chunks)
                   or (coll.metadata or {}).get("policy_hash") != phash):
        try:
            chroma.delete_collection(COLLECTION)
        except Exception:
            pass
        coll = chroma.create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine", "policy_hash": phash})
        coll.add(
            ids=[c["chunk_id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            embeddings=embed([c["text"] for c in chunks]),
            metadatas=[{"policy_id": c["policy_id"], "title": c["title"],
                        "section": c["section"], "category": c["category"],
                        "jurisdiction": c["jurisdiction"], "source": c["source"],
                        "chunk_id": c["chunk_id"]}
                       for c in chunks],
        )
        logger.info(f"[rag] indexed {len(chunks)} chunks from {len(policies)} policies")

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
            "policy_id": meta.get("policy_id"),
            "chunk_id": meta.get("chunk_id"),
            "title": meta.get("title"),
            "section": meta.get("section"),
            "category": meta.get("category"),
            "jurisdiction": meta.get("jurisdiction"),
            "source": meta.get("source"),
            "content": doc,
            "retrieval_score": round(max(0.0, 1 - dist), 3),         # cosine -> similarity
            "rerank_score": round(1 / (1 + math.exp(-float(logit))), 3),  # sigmoid -> 0..1
        })

    citations.sort(key=lambda c: c["rerank_score"], reverse=True)
    return citations[:n]
