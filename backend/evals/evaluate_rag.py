"""
Evaluate policy retrieval (RAG) against the golden cases.

Metric
  policy_retrieval_accuracy -- did the RAG layer retrieve the expected governing
  policy for each typology (recall@k)? A case "hits" if at least one expected
  policy id appears in the retrieved citations.

Needs the embedding model (Ollama) running. If it is unavailable, the eval is
skipped rather than failed.

Run:  python evals/evaluate_rag.py
"""

from _common import load_cases, pct

K = 5   # candidates retrieved before scoring recall


def main() -> bool:
    cases = [c for c in load_cases() if c.get("expected_policy_ids")]

    try:
        from app.tools.rag import search_policies
        # a cheap probe so we fail fast with a clear message if Ollama is down
        search_policies("structuring", k=1, n=1)
    except Exception as exc:
        print("=" * 78)
        print("RAG EVALUATION  --  SKIPPED (embedding model unavailable)")
        print(f"  reason: {exc}")
        print("  Start Ollama (qwen2.5 + nomic-embed-text) and re-run.")
        print("=" * 78)
        return True

    print("=" * 78)
    print("RAG / POLICY RETRIEVAL EVALUATION")
    print("=" * 78)
    hits = 0
    recalls = []
    for c in cases:
        cites = search_policies(c["alert"]["reason"], k=K, n=K)
        got = {p["policy_id"] for p in cites}
        expected = set(c["expected_policy_ids"])
        found = expected & got
        recall = len(found) / len(expected)
        recalls.append(recall)
        hit = bool(found)
        hits += hit
        print(f"\n{c['case_id']}")
        print(f"  expected : {sorted(expected)}")
        print(f"  retrieved: {sorted(got)}")
        print(f"  found    : {sorted(found) or '-'}  recall={recall:.0%}  {'PASS' if hit else 'FAIL'}")

    n = len(cases)
    mean_recall = sum(recalls) / n if n else 0
    print("\n" + "=" * 78)
    print("METRICS")
    print("-" * 78)
    print(f"  policy_retrieval_accuracy (>=1 hit) : {pct(hits, n)}  ({hits}/{n})")
    print(f"  mean recall@{K}                      : {mean_recall:.0%}")
    print("=" * 78)
    print("RESULT:", "ALL CASES RETRIEVED A GOVERNING POLICY" if hits == n else "SOME CASES MISSED")
    return hits == n


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
