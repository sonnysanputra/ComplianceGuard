"""
Evaluate the deterministic detection + routing layer against the golden cases.

Metrics
  typology_accuracy                 -- detected typology == expected
  risk_score_within_expected_range  -- rule baseline >= expected_min_score
  routing_accuracy                  -- fail-safe route == expected
  false_positive_clearance_accuracy -- FP review clears (or not) as expected

Run:  python evals/evaluate_rules.py
"""

from _common import load_cases, build_state, route_label, pct


def _fp_cleared(case: dict, state: dict) -> bool:
    """Run the false-positive review for a case and return True if it auto-clears."""
    import app.agents.stage4_disposition.false_positive_review as fp
    fp.get_customer = lambda cid: case["customer"]
    fp.get_transactions = lambda cid: case["transactions"]
    out = fp.false_positive_review.run(state)["fp_review"]
    return not out["requires_human_review"]


def main() -> bool:
    cases = load_cases()
    typ_ok = score_ok = route_ok = fp_ok = fp_total = 0

    print("=" * 78)
    print("RULE / DETECTION EVALUATION  (golden AML scenarios)")
    print("=" * 78)
    for c in cases:
        st = build_state(c)
        t_ok = st["typology"] == c["expected_typology"]
        s_ok = st["rule_score"] >= c["expected_min_score"]
        rl = route_label(st)
        r_ok = rl == c["expected_route"]
        typ_ok += t_ok; score_ok += s_ok; route_ok += r_ok

        fp_str = ""
        if "expected_fp_clearance" in c:
            fp_total += 1
            cleared = _fp_cleared(c, st)
            f_ok = cleared == c["expected_fp_clearance"]
            fp_ok += f_ok
            fp_str = f" | FP-clear={'PASS' if f_ok else 'FAIL'}"

        print(f"\n{c['case_id']}")
        print(f"  typology : {st['typology']:<26} expect {c['expected_typology']:<26} {'PASS' if t_ok else 'FAIL'}")
        print(f"  score    : {st['rule_score']:<3} (>= {c['expected_min_score']})"
              f"{'':<22} {'PASS' if s_ok else 'FAIL'}")
        print(f"  route    : {rl:<26} expect {c['expected_route']:<26} {'PASS' if r_ok else 'FAIL'}{fp_str}")

    n = len(cases)
    print("\n" + "=" * 78)
    print("METRICS")
    print("-" * 78)
    print(f"  typology_accuracy                 : {pct(typ_ok, n)}  ({typ_ok}/{n})")
    print(f"  risk_score_within_expected_range  : {pct(score_ok, n)}  ({score_ok}/{n})")
    print(f"  routing_accuracy                  : {pct(route_ok, n)}  ({route_ok}/{n})")
    print(f"  false_positive_clearance_accuracy : {pct(fp_ok, fp_total)}  ({fp_ok}/{fp_total})")
    print("=" * 78)

    passed = (typ_ok == n and score_ok == n and route_ok == n and fp_ok == fp_total)
    print("RESULT:", "ALL GOLDEN CASES PASSED" if passed else "SOME CASES FAILED")
    return passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
