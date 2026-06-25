"""
Policy document management: upload -> list -> get -> delete, all without
restarting the server. File I/O is redirected to a temp dir so tests stay clean.
"""

import importlib
import pytest


@pytest.fixture
def rag(tmp_path, monkeypatch):
    import app.tools.rag as rag
    # redirect the policy folder to a temp dir and stub the vector re-index
    monkeypatch.setattr(rag, "POLICIES_DIR", str(tmp_path))
    monkeypatch.setattr(rag, "reset_policy_collection", lambda: None)
    return rag


def test_upload_then_get_then_delete(rag):
    md = ("---\nid: MY-TEST-01\ntitle: Test Policy\nsection: 1\ncategory: AML\n---\n"
          "Customers must be screened against sanctions lists.").encode("utf-8")

    saved = rag.save_uploaded_policy("test_policy.md", md)
    assert saved["id"] == "MY-TEST-01" and saved["filename"] == "test_policy.md"

    # it now shows up in the loaded set and is fetchable by id
    assert any(p["id"] == "MY-TEST-01" for p in rag.load_policies())
    got = rag.get_policy("MY-TEST-01")
    assert got and "sanctions" in got["text"]

    # delete removes it
    assert rag.delete_policy("MY-TEST-01") is True
    assert rag.get_policy("MY-TEST-01") is None
    assert rag.delete_policy("MY-TEST-01") is False     # already gone


def test_upload_rejects_unsupported_type(rag):
    with pytest.raises(ValueError):
        rag.save_uploaded_policy("malware.exe", b"nope")


def test_upload_strips_path_traversal(rag, tmp_path):
    rag.save_uploaded_policy("../../evil.md", b"# just content here")
    # saved as a bare filename inside the policy dir, not outside it
    assert (tmp_path / "evil.md").exists()
