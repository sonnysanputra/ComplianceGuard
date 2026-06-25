"""
Supabase (Postgres) access layer -- the relational database.

Tool functions for the agents to fetch customer, transaction, and watchlist
data. Pure data lookups (no LLM), so they cost nothing in model terms.
"""

import os
from supabase import create_client, Client

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


def get_watchlist() -> list[dict]:
    """Active watchlist entities across all lists (sanctions, PEP, blacklist, etc.)."""
    res = _db().table("watchlist_entities").select("*").eq("is_active", True).execute()
    return res.data
