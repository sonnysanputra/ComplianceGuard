"""
Account behaviour baseline.

A transaction is suspicious mostly RELATIVE to the customer's own normal pattern.
This module derives a behavioural baseline from the account's established history
(amounts, countries, recipients, usual hours, dormancy) and then measures how far
the flagged activity deviates from it.

The deviations map to SC red-flag indicators: large withdrawals from
dormant/inactive accounts, sudden unexpectedly large activity, transfers to new
geographies, and bursts outside the customer's usual behaviour.

Pure functions -- no I/O, no LLM.
"""

from datetime import datetime


def _parse(dt):
    try:
        return datetime.fromisoformat(dt) if dt else None
    except (ValueError, TypeError):
        return None


def compute_baseline(transactions: list) -> dict:
    """Derive the account's normal behaviour from its established (non-new-recipient)
    history. Returns the baseline metrics surfaced to the analyst."""
    hist = [t for t in transactions if not t.get("is_new_recipient")]
    hist_out = [t for t in hist if t.get("direction", "out") == "out"]
    amounts = [t.get("amount", 0) for t in hist_out]
    times = [d for d in (_parse(t.get("date_time")) for t in hist) if d]
    hours = sorted(d.hour for d in times)

    if times:
        span_days = max((max(times) - min(times)).days, 1)
        months = max(span_days / 30.0, 1.0)
    else:
        months = 1.0

    return {
        "avg_monthly_outgoing": round(sum(amounts) / months) if amounts else 0,
        "max_single_transaction_90d": max(amounts) if amounts else 0,
        "usual_countries": sorted({t.get("country") for t in hist if t.get("country")}),
        "usual_recipients": sorted({t.get("recipient") for t in hist if t.get("recipient")}),
        "usual_transaction_hours": f"{hours[0]:02d}:00-{hours[-1]:02d}:00" if hours else "n/a",
        "new_recipient_rate": round(
            sum(1 for t in transactions if t.get("is_new_recipient")) / len(transactions), 2)
        if transactions else 0.0,
        "last_activity_date": max(times).isoformat() if times else None,
        "history_count": len(hist),
    }


def behavior_deviations(transactions: list, alert: dict, cfg: dict) -> list[dict]:
    """Compare the flagged (new-recipient outgoing) activity against the baseline.
    Returns a list of triggered deviations, each shaped for the rule engine:
    {rule_id, name, points, severity, evidence, evidence_items}."""
    base = compute_baseline(transactions)
    recent = [t for t in transactions
              if t.get("is_new_recipient") and t.get("direction", "out") == "out"]
    fired = []

    def tx_ev(t, field, value, desc):
        return {"source_type": "transaction", "source_id": t.get("transaction_id"),
                "field": field, "value": value, "description": desc}

    def emit(c, evidence, items):
        fired.append({"rule_id": c["rule_id"], "name": c["name"], "points": c["points"],
                      "severity": c.get("severity", "MEDIUM"),
                      "evidence": evidence, "evidence_items": items})

    if not recent:
        return fired

    # 1. amount far above the account's historical maximum
    c = cfg.get("amount_spike"); mult = cfg.get("amount_spike_multiplier", 5)
    cap = base["max_single_transaction_90d"]
    if c and cap:
        spikes = [t for t in recent if t.get("amount", 0) > mult * cap]
        if spikes:
            top = max(spikes, key=lambda t: t.get("amount", 0))
            emit(c, f"RM{top['amount']:,} is over {mult}x the account's historical max (RM{cap:,}).",
                 [tx_ev(top, "amount", top["amount"], "Amount far above the account baseline")])

    # 2. transfer to a country never seen before
    c = cfg.get("new_country")
    if c and base["usual_countries"]:
        nc = [t for t in recent if t.get("country") and t["country"] not in base["usual_countries"]]
        if nc:
            t = nc[0]
            emit(c, f"Transfer to {t['country']} -- not in account history "
                    f"({', '.join(base['usual_countries'])}).",
                 [tx_ev(t, "country", t["country"], "New destination country vs baseline")])

    # 3. activity outside the customer's usual hours
    c = cfg.get("off_hours")
    if c:
        start, end = c.get("start", 9), c.get("end", 18)
        off = [(t, d) for t in recent if (d := _parse(t.get("date_time")))
               and (d.hour < start or d.hour >= end)]
        if off:
            t, d = off[0]
            emit(c, f"Transfer at {d.strftime('%H:%M')} is outside usual hours "
                    f"({base['usual_transaction_hours']}).",
                 [tx_ev(t, "date_time", d.strftime('%H:%M'), "Activity outside usual transacting hours")])

    # 4. high-value transfer to a brand-new recipient
    c = cfg.get("new_recipient_high")
    if c:
        thr = c.get("amount_threshold", 10000)
        nrh = [t for t in recent if t.get("amount", 0) >= thr]
        if nrh:
            t = max(nrh, key=lambda x: x.get("amount", 0))
            emit(c, f"RM{t['amount']:,} to new recipient '{t.get('recipient')}'.",
                 [tx_ev(t, "amount", t["amount"], "High-value transfer to a brand-new recipient")])

    # 5. dormant account suddenly active (SC red flag)
    c = cfg.get("dormancy")
    if c and base["last_activity_date"]:
        last = _parse(base["last_activity_date"])
        firsts = [d for t in recent if (d := _parse(t.get("date_time")))]
        if last and firsts:
            gap = (min(firsts) - last).days
            if gap >= c.get("days", 90):
                emit(c, f"Account was dormant ~{gap} days, then sudden activity.",
                     [{"source_type": "customer_profile", "source_id": alert.get("customer_id", "unknown"),
                       "field": "dormancy_days", "value": gap,
                       "description": "Large activity after a long period of dormancy"}])

    return fired
