"""
RAG chunking: long policies are split into section-level chunks with per-chunk
metadata, so citations map to an actual section, not the whole document.
"""

from app.tools.rag import chunk_policy, chunk_by_headings, chunk_policy_doc


def test_sliding_window_overlaps_and_covers():
    text = "x" * 2000
    chunks = chunk_policy(text, chunk_size=800, overlap=120)
    assert len(chunks) >= 3
    assert all(len(c) <= 800 for c in chunks)
    # overlap: the tail of chunk 0 reappears at the head of chunk 1
    assert chunks[0][-120:] == chunks[1][:120]


def test_short_text_is_one_chunk():
    assert chunk_policy("short policy text") == ["short policy text"]


def test_overlap_never_causes_infinite_loop():
    # overlap >= chunk_size must still terminate
    assert len(chunk_policy("y" * 500, chunk_size=100, overlap=999)) >= 5


def test_chunk_by_headings_splits_on_markdown_sections():
    text = ("Intro preamble.\n"
            "## Section 1 Scope\nScope body.\n"
            "## Section 11.3 Suspicious Transaction Review\nSTR body here.")
    secs = chunk_by_headings(text)
    titles = [t for t, _ in secs]
    assert "Section 1 Scope" in titles
    assert "Section 11.3 Suspicious Transaction Review" in titles
    # the preamble before the first heading is preserved
    assert any(t is None and "preamble" in body for t, body in secs)


def test_chunk_policy_doc_metadata_and_ids():
    policy = {
        "id": "MY-AML-STR-001",
        "title": "Malaysia Suspicious Transaction Review Policy",
        "section": "", "category": "AML", "jurisdiction": "Malaysia", "source": "SC",
        "text": "## Section 1\nbody one is long enough.\n## Section 11.3\nstr review body content.",
    }
    chunks = chunk_policy_doc(policy)
    assert len(chunks) == 2
    assert [c["chunk_id"] for c in chunks] == ["MY-AML-STR-001-001", "MY-AML-STR-001-002"]
    assert chunks[1]["section"] == "Section 11.3"
    assert chunks[0]["policy_id"] == "MY-AML-STR-001"
    assert chunks[0]["title"].startswith("Malaysia")


def test_long_section_is_subchunked_by_size():
    policy = {"id": "P1", "title": "T", "section": "", "category": "AML",
              "jurisdiction": "MY", "source": "SC",
              "text": "## Big\n" + ("z" * 2000)}
    chunks = chunk_policy_doc(policy, chunk_size=800, overlap=100)
    assert len(chunks) >= 3                      # one section, split by size
    assert all(c["section"] == "Big" for c in chunks)
    assert chunks[-1]["chunk_id"] == f"P1-{len(chunks):03d}"
