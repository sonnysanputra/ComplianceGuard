"""Tests for the deterministic bank-statement transaction parser."""

from app.tools.statement_parse import parse_statement

# A Maybank-style reconstructed statement (one transaction per line:
# DATE  DESCRIPTION [REF]  AMOUNT  RUNNING-BALANCE).
STATEMENT = """\
01/06/2026 BEGINNING BALANCE 12,450.00
03/06/2026 SALARY CREDIT - ACME SDN BHD 4,000.00 16,450.00
05/06/2026 DUITNOW QR PAYMENT SPEEDMART 120.00 16,330.00
22/06/2026 IBG TRANSFER TO GLOBAL TRADE LTD IBG9001 9,800.00 6,530.00
22/06/2026 IBG TRANSFER TO GLOBAL TRADE LTD IBG9002 9,800.00 -3,270.00
24/06/2026 DUITNOW TRSF CR FR SARAH LIM 5,000.00 1,730.00
28/06/2026 ENDING BALANCE 1,730.00
"""


def test_skips_opening_and_closing_balance_lines():
    rows = parse_statement(STATEMENT)
    descs = " ".join(r["recipient"].lower() for r in rows)
    assert "balance" not in descs
    assert len(rows) == 5  # 5 real transactions, opening/closing excluded


def test_direction_from_running_balance_delta():
    rows = parse_statement(STATEMENT)
    by_recipient = {r["recipient"]: r for r in rows}
    assert by_recipient["ACME SDN BHD"]["direction"] == "in"     # balance rose
    assert by_recipient["SPEEDMART"]["direction"] == "out"       # balance fell
    assert by_recipient["SARAH LIM"]["direction"] == "in"        # credit


def test_amount_is_not_the_running_balance():
    rows = parse_statement(STATEMENT)
    structuring = [r for r in rows if r["recipient"] == "GLOBAL TRADE LTD"]
    assert len(structuring) == 2
    assert all(r["amount"] == 9800 for r in structuring)         # amount, not balance
    assert all(r["direction"] == "out" for r in structuring)


def test_iso_date_conversion():
    rows = parse_statement(STATEMENT)
    assert rows[0]["date_time"] == "2026-06-03T00:00:00"


def test_non_statement_text_yields_nothing():
    assert parse_statement("This is just a narrative alert with no tabular rows.") == []
