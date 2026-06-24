"""
Run the CompliGuard investigation on the demo alert end-to-end.

  python main.py

The graph runs all agents, PAUSES at human approval (human-in-the-loop),
prints the SAR draft for review, then we 'approve' and it finishes.
"""

import app.core.config  # noqa: F401 -- importing this loads .env before anything else

from langgraph.types import Command
from app.orchestrator import build_graph
from app.data.scenarios import SCENARIOS
from app.services.persistence import persist_case, persist_decision


def pick_scenario() -> dict:
    """Let the user choose which demo alert to investigate."""
    print("\nSelect a case to investigate:")
    for i, s in enumerate(SCENARIOS, 1):
        print(f"  {i}. {s['id']}  ({s['customer_id']})  -- {s['_expected']}")
    choice = input(f"\nEnter 1-{len(SCENARIOS)} (default 1): ").strip()
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS) else 0
    return SCENARIOS[idx]


def main():
    graph = build_graph()

    alert = pick_scenario()

    # one thread per case -- enables the pause/resume
    config = {"configurable": {"thread_id": alert["id"]}}

    print("=" * 70)
    print(f"  INVESTIGATING {alert['id']}")
    print("=" * 70)

    # strip internal hint keys (e.g. _expected) before the graph sees the alert
    clean_alert = {k: v for k, v in alert.items() if not k.startswith("_")}

    # Run until the graph hits human_approval and pauses (or ends early if low-risk)
    result = graph.invoke({"alert": clean_alert}, config)

    # ---- Show the investigation result so far ----
    snap = graph.get_state(config).values

    tri = snap.get("triage", {})
    kyc = snap.get("kyc_findings", {})
    wl = snap.get("watchlist_findings", {})
    mem = snap.get("memory_findings", {})
    rev = snap.get("review", {})

    print("\n" + "-" * 70)
    print("CASE TRIAGE & KEY FINDINGS:")
    print("-" * 70)
    print(f"  Triage     : {tri.get('alert_type')} | {tri.get('severity')} severity | priority {tri.get('priority')}")
    print(f"  Typology   : {snap.get('transaction_findings', {}).get('typology')}")
    print(f"  KYC        : {kyc.get('consistency', '?')} | {len(kyc.get('checks_failed', []))} checks failed"
          f"{'  -> EDD REQUIRED' if kyc.get('edd_required') else ''}")
    if kyc.get("key_concern") and kyc.get("key_concern") != "none":
        print(f"               key concern: {kyc.get('key_concern')}")
    print(f"  Watchlist  : {wl.get('verdict')} "
          f"(best {wl.get('match_score')}% on {wl.get('list_type')})")
    print(f"  Memory     : {mem.get('memory_risk_signal')} [{mem.get('memory_risk_direction')}]")
    pols = snap.get("retrieved_policies", [])
    if pols:
        cites = " | ".join(f"{p['policy_id']} {p['title']} "
                           f"(retr {p['retrieval_score']:.0%}, rerank {p['rerank_score']:.0%})"
                           for p in pols)
        print(f"  Policies   : {cites}")

    print(f"\nRisk Score : {snap.get('risk_score')}/100  ({snap.get('risk_level')})")
    print(f"   ├─ rule-based baseline : {snap.get('rule_score')}/100")
    print(f"   └─ Qwen AI assessment  : {snap.get('ai_score')}/100")

    factors = snap.get("risk_factors", [])
    if factors:
        print("\nRisk Factor Breakdown:")
        for f in factors:
            sign = "+" if f["points"] >= 0 else ""
            print(f"   {sign}{f['points']:>3}  {f['factor']:<28} — {f['evidence']}")
        raw = sum(f["points"] for f in factors)
        if raw != snap.get("rule_score"):
            print(f"   ───  raw total {raw}, capped to {snap.get('rule_score')}/100")

    print(f"\nRecommend  : {snap.get('recommendation')}")
    print(f"\nRisk Explanation (Qwen):\n{snap.get('risk_explanation')}")

    if snap.get("sar_draft"):
        print("\n" + "-" * 70)
        print("SAR DRAFT (for human review):")
        print("-" * 70)
        print(snap["sar_draft"])

        print("\n" + "-" * 70)
        print("COMPLIANCE REVIEW:")
        print("-" * 70)
        print(f"  Status        : {rev.get('status')}")
        print(f"  Completeness  : {rev.get('completeness_score')}  |  Quality: {rev.get('quality_score')}/100")
        print(f"  Claims backed : {rev.get('claims_supported')}")
        if rev.get("unsupported_claims"):
            print(f"  Flagged       : {rev.get('unsupported_claims')}")

    # ---- Per-agent confidence (from the A2A message log) ----
    print("\n" + "-" * 70)
    print("AGENT CONFIDENCE:")
    print("-" * 70)
    for msg in snap.get("a2a_messages", []):
        conf = msg.get("confidence")
        conf_str = f"{conf * 100:.0f}%" if isinstance(conf, (int, float)) else "n/a"
        print(f"  {msg['from']:<22} {msg.get('status', ''):<6} "
              f"confidence={conf_str:<5} ({msg.get('duration_ms', 0)}ms)")

    print("\n" + "-" * 70)
    print("AUDIT TIMELINE:")
    print("-" * 70)
    for line in sorted(snap.get("audit", [])):
        print(" ", line)

    # ---- Human-in-the-loop: the graph pauses for a structured decision ----
    if "__interrupt__" in result:
        # request_more_info re-runs the investigation, so loop until a final decision
        while "__interrupt__" in result:
            persist_case(graph.get_state(config).values, status="awaiting_decision")
            print("\n" + "=" * 70)
            print("  ⏸  PAUSED — analyst decision required")
            print("=" * 70)
            decision = input("Decision (approve / reject / edit / request_more_info): ").strip() or "approve"
            note = None
            if decision in ("reject", "request_more_info"):
                note = input("Reason / info needed: ").strip() or None

            payload = {"decision": decision, "analyst_id": "cli-analyst", "analyst_note": note}
            result = graph.invoke(Command(resume=payload), config)
            final = graph.get_state(config).values
            persist_decision(final["alert"]["id"], decision,
                             analyst_id="cli-analyst", notes=note)

            if decision == "request_more_info" and "__interrupt__" in result:
                print("\n🔁 Re-investigating with the request on record...")
                continue
            persist_case(final, status="closed")
            print(f"\n✅ Case closed. Decision: {decision}"
                  + (f" — {note}" if note else ""))
            break
    else:
        # Low-risk path: scored under threshold, exited before SAR drafting
        persist_case(snap, status="auto_closed")
        print("\n" + "=" * 70)
        print("  ✅ AUTO-CLOSED — low risk, no SAR needed (early exit saved LLM calls)")
        print("=" * 70)


if __name__ == "__main__":
    main()
