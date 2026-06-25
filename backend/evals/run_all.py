"""
Run the full evaluation suite against the golden AML scenarios.

  python evals/run_all.py

Exit code is non-zero if any non-skipped eval fails, so this can gate CI.
"""

import evaluate_rules
import evaluate_rag
import evaluate_sar_quality


def main() -> int:
    results = {}
    for name, fn in (("rules", evaluate_rules.main),
                     ("rag", evaluate_rag.main),
                     ("sar_quality", evaluate_sar_quality.main)):
        print()
        results[name] = fn()

    print("\n" + "#" * 78)
    print("EVALUATION SUMMARY")
    for name, ok in results.items():
        print(f"  {name:<14} {'PASS' if ok else 'FAIL'}")
    print("#" * 78)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
