"""
Supabase (Postgres) access layer -- the relational database.

Tool functions for the agents to fetch customer, transaction, and watchlist
data. Pure data lookups (no LLM), so they cost nothing in model terms.
"""

import os
import logging
import uuid
from supabase import create_client, Client

logger = logging.getLogger(__name__)
_client: Client | None = None


def _db() -> Client:
    """Lazily create the Supabase client on first use (reads env at call time)."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_KEY missing. Add them to your .env file."
            )
        _client = create_client(url, key)
    return _client


def client() -> Client:
    """Public accessor for the Supabase client (used by the persistence layer)."""
    return _db()


# ======================================================================
# TOOL FUNCTIONS  -- query Supabase, no LLM, no model cost
# ======================================================================
def get_customer(customer_id: str) -> dict | None:
    res = _db().table("customers").select("*").eq("customer_id", customer_id).execute()
    return res.data[0] if res.data else None


def get_transactions(customer_id: str) -> list[dict]:
    res = _db().table("transactions").select("*").eq("customer_id", customer_id).execute()
    return res.data


# ---- ingestion (for ad-hoc new investigations) ----
def upsert_customer(customer: dict) -> bool:
    """Create or update a customer profile so the agents have a KYC record."""
    try:
        _db().table("customers").upsert(customer).execute()
        return True
    except Exception as exc:
        logger.warning(f"[db] upsert_customer failed: {exc}")
        return False


def replace_transactions(customer_id: str, rows: list[dict]) -> int:
    """Replace a customer's transactions with the provided set, so the
    investigation analyses exactly what was ingested (idempotent on re-run)."""
    if not rows:
        return 0
    try:
        db = _db()
        db.table("transactions").delete().eq("customer_id", customer_id).execute()
        prepared = []
        for r in rows:
            r = {**r, "customer_id": customer_id}
            r.setdefault("transaction_id", f"TXN-{uuid.uuid4().hex[:10].upper()}")
            r.setdefault("transaction_type", "transfer")
            prepared.append(r)
        db.table("transactions").insert(prepared).execute()
        return len(prepared)
    except Exception as exc:
        logger.warning(f"[db] replace_transactions failed: {exc}")
        return 0


def get_watchlist() -> list[dict]:
    """Active watchlist entities across all lists (sanctions, PEP, blacklist, etc.)."""
    res = _db().table("watchlist_entities").select("*").eq("is_active", True).execute()
    return res.data


def get_transaction_edges() -> list[dict]:
    """Money-flow edges for relationship-graph analysis. Best-effort: returns []
    if the table is absent/unreachable (the graph agent then derives edges from
    the customer's own transactions)."""
    try:
        res = _db().table("transaction_edges").select("*").execute()
        return [{"from": e.get("from_account"), "to": e.get("to_account"),
                 "amount": e.get("amount"), "time": e.get("transaction_time")}
                for e in (res.data or [])]
    except Exception:
        return []
