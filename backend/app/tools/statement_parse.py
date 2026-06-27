"""
Deterministic bank-statement transaction parser.

Given the row-reconstructed text of a statement (see doc_extract._pdf_rows), this
pulls out the transactions WITHOUT an LLM. For tabular statements this is far more
reliable than asking the model to do running-balance arithmetic inline -- it never
drops rows and it derives direction from the balance delta every time.

Each transaction line is read as:  DATE  DESCRIPTION [REF]  AMOUNT  RUNNING-BALANCE
  - the last money value on the line is the running balance
  - the value before it is the transaction amount
  - direction = 'in' if the balance rose vs the previous line, else 'out'

Used for structured statements; the LLM path remains the fallback for prose alerts.
"""

import re

_DATE = re.compile(r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})")
_MONEY = re.compile(r"-?\d{1,3}(?:,\d{3})*\.\d{2}")  # Malaysian amounts always show 2 decimals
_REF = re.compile(r"\b[A-Z]{2,}\d{3,}\b")            # IBG9001, BPAY7781, etc.
_SKIP = ("beginning balance", "ending balance", "opening balance", "closing balance",
         "baki bawa", "brought forward", "carried forward", "b/f", "c/f")
_PREFIXES = (
    "ibg transfer to", "instant transfer to", "duitnow trsf cr fr", "duitnow trsf to",
    "duitnow qr payment", "duitnow payment", "transfer to", "payment to", "fpx payment",
    "jompay bill pymt", "jompay payment", "mae instant transfer", "mae transfer",
    "atm cash withdrawal", "cash withdrawal", "cash deposit", "salary credit",
    "interest credit", "svc charge", "service charge", "payment", "transfer",
)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _iso_date(d: str) -> str:
    d = d.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", d):
        return f"{d[:10]}T00:00:00"
    parts = re.split(r"[/-]", d)
    if len(parts) == 3:
        dd, mm, yy = parts
        if len(yy) == 2:
            yy = "20" + yy
        return f"{yy}-{int(mm):02d}-{int(dd):02d}T00:00:00"
    return d


def _clean_recipient(desc: str) -> str:
    d = _REF.sub("", desc).strip(" -")
    low = d.lower()
    for p in _PREFIXES:
        if low.startswith(p):
            return d[len(p):].strip(" -") or d
    return d


def parse_statement(text: str) -> list[dict]:
    """Return transaction dicts from a reconstructed statement (empty if not a statement)."""
    rows: list[dict] = []
    prev_balance: float | None = None
    for line in text.splitlines():
        dm = _DATE.match(line)
        if not dm:
            continue
        monies = _MONEY.findall(line)
        if not monies:
            continue
        low = line.lower()
        if any(s in low for s in _SKIP):
            prev_balance = _num(monies[-1])      # anchor the running balance, not a txn
            continue
        if len(monies) == 1:
            prev_balance = _num(monies[-1])      # balance-only line -> anchor
            continue

        amount = _num(monies[-2])
        balance = _num(monies[-1])
        if amount == 0:
            prev_balance = balance
            continue
        desc = line[dm.end(): line.find(monies[0])].strip()
        direction = "out"
        if prev_balance is not None:
            direction = "in" if balance > prev_balance else "out"
        prev_balance = balance
        rows.append({
            "date_time": _iso_date(dm.group(1)),
            "amount": int(round(amount)),
            "recipient": _clean_recipient(desc),
            "country": "Malaysia",
            "direction": direction,
            "is_new_recipient": True,
        })
    return rows
