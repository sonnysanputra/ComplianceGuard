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
from app.core.case_status import CaseStatus, status_for_decision


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

    # ---- Data quality gate: incomplete cases never reach the investigation ----
    dq = snap.get("data_quality", {})
    if dq and not dq.get("complete", True):
        tri = snap.get("triage", {})
        print("\n" + "=" * 70)
        print("  ⚠  NEEDS MORE INFORMATION — case cannot be reliably investigated")
        print("=" * 70)
        print(f"  Alert      : {alert['id']} ({tri.get('alert_type')})")
        print(f"  Missing    : {', '.join(dq.get('missing_fields', []))}")
        print(f"  Action     : {dq.get('recommended_action')}")
        print("\n  Audit:")
        for line in sorted(snap.get("audit", [])):
            print("   ", line)
        persist_case(snap, status=CaseStatus.NEEDS_MORE_INFORMATION)
        return

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
    cs, rs = wl.get("customer_screening", {}), wl.get("recipient_screening", {})
    print(f"  Watchlist  : customer={cs.get('verdict')} | recipient={rs.get('verdict')}"
          f"{' (' + str(rs.get('best_match')) + ', ' + str(rs.get('list_type')) + ' ' + str(rs.get('match_score')) + '%)' if rs.get('best_match') else ''}")
    if wl.get("required_action") and wl.get("is_match") or (rs.get("verdict") == "POSSIBLE_MATCH_REQUIRES_REVIEW"):
        print(f"               action: {wl.get('required_action')}")
    print(f"  Memory     : {mem.get('memory_risk_signal')} [{mem.get('memory_risk_direction')}]")
    pols = snap.get("retrieved_policies", [])
    if pols:
        cites = " | ".join(f"{p['policy_id']} {p['title']} "
                           f"(retr {p['retrieval_score']:.0%}, rerank {p['rerank_score']:.0%})"
                           for p in pols)
        print(f"  Policies   : {cites}")

    tl = (snap.get("timeline_findings") or {}).get("timeline", [])
    if tl:
        print("\n" + "-" * 70)
        print("TRANSACTION TIMELINE:")
        print("-" * 70)
        for e in tl:
            arrow = "IN <-" if str(e.get("direction")).upper() == "IN" else "OUT->"
            print(f"  {e.get('time')}  {arrow} RM{e.get('amount', 0):>7,}  "
                  f"{str(e.get('recipient'))[:22]:<22} {e.get('risk_note')}")

    errors = snap.get("errors", [])
    if errors:
        print("\n⚠  TOOL FAILURE(S) — case forced to manual review:")
        for e in errors:
            print(f"     - {e.get('agent')}: {e.get('error')}")

    print(f"\nRisk Score : {snap.get('risk_score')}/100  ({snap.get('risk_level')})")
    print(f"   ├─ rule-based baseline : {snap.get('rule_score')}/100")
    print(f"   └─ Qwen AI assessment  : {snap.get('ai_score')}/100")

    factors = snap.get("risk_factors", [])
    if factors:
        print("\nTriggered AML Rules (rule engine):")
        for f in factors:
            sign = "+" if f["points"] >= 0 else ""
            print(f"   [{f.get('rule_id', '')}] {sign}{f['points']:>3}  "
                  f"{f.get('name', '')} ({f.get('severity', '')}) — {f['evidence']}")
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

    # ---- False positive review (sub-threshold cases) ----
    fp = snap.get("fp_review")
    if fp:
        print("\n" + "-" * 70)
        print("FALSE POSITIVE REVIEW:")
        print("-" * 70)
        print(f"  Likelihood    : {fp.get('false_positive_likelihood')}")
        print(f"  Checks        : {fp.get('checks')}")
        print(f"  Reason        : {fp.get('clearance_reason')}")
        print(f"  Risk adj.     : {fp.get('risk_adjustment')}")
        print(f"  Action        : {fp.get('recommended_action')}")
        print(f"  Needs human   : {fp.get('requires_human_review')}")

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
            persist_case(graph.get_state(config).values,
                         status=CaseStatus.AWAITING_ANALYST_REVIEW)
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
            persist_case(final, status=status_for_decision(decision))
            print(f"\n✅ Case {status_for_decision(decision)}. Decision: {decision}"
                  + (f" — {note}" if note else ""))
            break
    elif snap.get("fp_review") and not snap["fp_review"].get("requires_human_review"):
        # Sub-threshold case cleared by the false-positive review
        persist_case(snap, status=CaseStatus.LOW_RISK_AUTO_CLEARED)
        print("\n" + "=" * 70)
        print("  ✅ AUTO-CLOSED as FALSE POSITIVE — "
              f"{snap['fp_review'].get('recommended_action')}")
        print("=" * 70)
    else:
        # Low-risk path: scored under threshold, nothing triggered
        persist_case(snap, status=CaseStatus.LOW_RISK_AUTO_CLEARED)
        print("\n" + "=" * 70)
        print("  ✅ AUTO-CLOSED — low risk, no SAR needed (early exit saved LLM calls)")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as exc:
        msg = str(exc)
        print(f"\n❌ Error: {type(exc).__name__}: {exc}")
        if "11434" in msg or "Connection" in msg or "connect" in msg.lower():
            print("   → Is Ollama running? Start it, then `ollama list` to confirm "
                  "qwen2.5 + nomic-embed-text are installed.")
        if "SUPABASE" in msg.upper():
            print("   → Check your backend/.env Supabase URL and secret key.")
