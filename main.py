"""
Run the CompliGuard investigation on the demo alert end-to-end.

  python main.py

The graph runs all agents, PAUSES at human approval (human-in-the-loop),
prints the SAR draft for review, then we 'approve' and it finishes.
"""

from dotenv import load_dotenv
load_dotenv()  # must run BEFORE importing the orchestrator (which reads env vars)

from langgraph.types import Command
from src.orchestrator import build_graph
from src.scenarios import SCENARIOS


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
    print(f"\nRisk Score : {snap.get('risk_score')}/100")
    print(f"Recommend  : {snap.get('recommendation')}")
    print(f"\nRisk Explanation:\n{snap.get('risk_explanation')}")

    if snap.get("sar_draft"):
        print("\n" + "-" * 70)
        print("SAR DRAFT (for human review):")
        print("-" * 70)
        print(snap["sar_draft"])

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

    # ---- Human-in-the-loop: the graph is paused, waiting for a decision ----
    if "__interrupt__" in result:
        print("\n" + "=" * 70)
        print("  ⏸  PAUSED — waiting for human analyst decision")
        print("=" * 70)
        decision = input("Approve escalation? (approve / reject / edit): ").strip() or "approve"

        # Resume the graph from exactly where it paused
        graph.invoke(Command(resume=decision), config)
        final = graph.get_state(config).values
        print(f"\n✅ Case closed. Human decision recorded: {final['human_decision']}")
    else:
        # Low-risk path: scored under threshold, exited before SAR drafting
        print("\n" + "=" * 70)
        print("  ✅ AUTO-CLOSED — low risk, no SAR needed (early exit saved LLM calls)")
        print("=" * 70)


if __name__ == "__main__":
    main()
