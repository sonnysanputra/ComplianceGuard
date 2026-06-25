"""
Relationship-graph analysis for layering / money-mule detection.

Money laundering is a NETWORK behaviour: funds fan out across many accounts,
get forwarded hop-by-hop to obscure the trail, converge on a common collector,
or loop back to the origin. Looking at one transaction at a time misses this --
so this tool builds a directed money-flow graph and computes network features.

It works from a real edge table (transaction_edges) when one exists, and falls
back to deriving edges from the customer's own transactions. Pure analysis -- the
DB read is the only I/O and is best-effort.

analyze_account(account, transactions, edges) -> {
    fan_out_count, fan_in_count, hop_count, common_recipient,
    circular_flow, rapid_forwarding_detected, possible_layering_path, graph_risk_score
}
"""

from collections import defaultdict
from datetime import datetime

RAPID_HOURS = 24          # in -> out within this window reads as forwarding
MAX_GRAPH_SCORE = 30
_MAX_NODES = 500          # guard the DFS on pathological inputs


def _parse(t):
    try:
        return datetime.fromisoformat(t) if t else None
    except (ValueError, TypeError):
        return None


def transactions_to_edges(account: str, transactions: list) -> list[dict]:
    """Derive money-flow edges from a single account's transactions."""
    edges = []
    for t in transactions:
        amt, tm = t.get("amount", 0), t.get("date_time")
        if t.get("direction") == "in":
            edges.append({"from": t.get("recipient") or "EXTERNAL", "to": account,
                          "amount": amt, "time": tm})
        else:
            edges.append({"from": account, "to": t.get("recipient") or "EXTERNAL",
                          "amount": amt, "time": tm})
    return edges


def _component(edges: list, root: str) -> list[dict]:
    """Edges in root's (undirected) connected component, or [] if root absent."""
    if not any(e["from"] == root or e["to"] == root for e in edges):
        return []
    seen, changed = {root}, True
    while changed:
        changed = False
        for e in edges:
            if e["from"] in seen and e["to"] not in seen:
                seen.add(e["to"]); changed = True
            if e["to"] in seen and e["from"] not in seen:
                seen.add(e["from"]); changed = True
    return [e for e in edges if e["from"] in seen and e["to"] in seen]


def analyze_graph(edges: list, root: str) -> dict:
    """Compute network features of the money-flow graph as seen from `root`."""
    adj = defaultdict(list)       # from -> [(to, amount, time)]
    rev = defaultdict(set)        # to -> {from}
    nodes = set()
    for e in edges:
        adj[e["from"]].append((e["to"], e.get("amount", 0), _parse(e.get("time"))))
        rev[e["to"]].add(e["from"])
        nodes.update((e["from"], e["to"]))

    fan_out = len({to for to, _, _ in adj.get(root, [])})
    fan_in = len(rev.get(root, set()))

    # rapid forwarding: any node receives funds and pushes them out within the window
    rapid = False
    for node in nodes:
        ins = [d for e in edges if e["to"] == node and (d := _parse(e.get("time")))]
        outs = [tm for _, _, tm in adj.get(node, []) if tm]
        if any(0 <= (o - i).total_seconds() / 3600 <= RAPID_HOURS for i in ins for o in outs):
            rapid = True
            break

    # longest forwarding chain from root (DFS, no revisiting -> no infinite loops)
    best = [root]

    def dfs(node, path, visited):
        nonlocal best
        nxt = [to for to, _, _ in adj.get(node, []) if to not in visited]
        if not nxt and len(path) > len(best):
            best = path
        for to in nxt:
            if len(visited) < _MAX_NODES:
                dfs(to, path + [to], visited | {to})
    dfs(root, [root], {root})
    hop_count = len(best) - 1

    # circular flow: can funds leave root and return to it?
    def reaches_root(node, visited):
        for to, _, _ in adj.get(node, []):
            if to == root:
                return True
            if to not in visited and reaches_root(to, visited | {to}):
                return True
        return False
    circular = reaches_root(root, {root})

    # common recipient: a node collecting funds from 2+ distinct senders (mule convergence)
    common = sorted(n for n in nodes if len(rev.get(n, set())) >= 2)

    score = 0
    if fan_out >= 5:
        score += 10                       # dispersion / fan-out
    if rapid:
        score += 10                       # rapid forwarding (mule)
    if hop_count >= 3:
        score += 5                        # deep forwarding chain
    if circular:
        score += 10                       # round-tripping
    if common:
        score += 5                        # convergence on a collector
    score = min(score, MAX_GRAPH_SCORE)

    return {
        "fan_out_count": fan_out,
        "fan_in_count": fan_in,
        "hop_count": hop_count,
        "common_recipient": common[:5],
        "circular_flow": circular,
        "rapid_forwarding_detected": rapid,
        "possible_layering_path": best,
        "graph_risk_score": score,
    }


def analyze_account(account: str, transactions: list, edges: list | None = None) -> dict:
    """Analyse an account's money-flow network. Prefers the real edge table's
    connected component for `account`; otherwise derives edges from its
    transactions."""
    component = _component(edges or [], account)
    use = component if component else transactions_to_edges(account, transactions)
    return analyze_graph(use, account)
