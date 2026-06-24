"""
Persistence service -- writes completed cases and their full audit trail to
Supabase so case history survives restarts and is queryable (a compliance
requirement).

All writes are BEST-EFFORT: if the audit tables don't exist yet or the DB is
unreachable, the investigation still succeeds -- persistence just logs a warning.
Run schema_cases.sql in Supabase to create the tables.
"""

import logging
from datetime import datetime, timezone

from app.tools.db import client

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_case(state: dict, status: str) -> bool:
    """Save (upsert) a case row plus its events, agent outputs, risk
    assessment, and SAR draft. Idempotent -- re-running a case replaces its
    child rows rather than duplicating them."""
    try:
        alert = state.get("alert", {})
        case_id = alert.get("id")
        if not case_id:
            return False

        db = client()
        tri = state.get("triage", {})
        tf = state.get("transaction_findings", {})

        # 1) the case row (upsert on case_id)
        db.table("cases").upsert({
            "case_id":        case_id,
            "customer_id":    alert.get("customer_id"),
            "alert_reason":   alert.get("reason"),
            "recipient":      alert.get("recipient"),
            "alert_type":     tri.get("alert_type"),
            "typology":       tf.get("typology"),
            "priority":       tri.get("priority"),
            "status":         status,
            "risk_score":     state.get("risk_score"),
            "rule_score":     state.get("rule_score"),
            "ai_score":       state.get("ai_score"),
            "risk_level":     state.get("risk_level"),
            "recommendation": state.get("recommendation"),
            "updated_at":     _now(),
        }).execute()

        # clear child rows so a re-run doesn't duplicate them
        for tbl in ("case_events", "agent_outputs", "risk_assessments", "sar_drafts"):
            db.table(tbl).delete().eq("case_id", case_id).execute()

        # 2) events + 3) structured outputs, both from the CoT traces
        events, outputs = [], []
        for t in state.get("cot_traces", []):
            events.append({
                "case_id":    case_id,
                "agent_name": t.get("agent"),
                "event_type": "reasoning",
                "message":    (t.get("reasoning") or "")[:1000],
                "confidence": t.get("confidence"),
            })
            outputs.append({
                "case_id":     case_id,
                "agent_name":  t.get("agent"),
                "output":      t.get("output") or {},
                "confidence":  t.get("confidence"),
                "duration_ms": t.get("duration_ms"),
            })
        if events:
            db.table("case_events").insert(events).execute()
        if outputs:
            db.table("agent_outputs").insert(outputs).execute()

        # 4) risk assessment
        if state.get("risk_score") is not None:
            db.table("risk_assessments").insert({
                "case_id":     case_id,
                "rule_score":  state.get("rule_score"),
                "ai_score":    state.get("ai_score"),
                "final_score": state.get("risk_score"),
                "risk_level":  state.get("risk_level"),
                "key_drivers": state.get("key_drivers") or [],
                "explanation": state.get("risk_explanation"),
            }).execute()

        # 5) SAR draft (only high-risk cases produce one)
        if state.get("sar_draft"):
            rev = state.get("review", {})
            db.table("sar_drafts").insert({
                "case_id":          case_id,
                "draft_text":       state.get("sar_draft"),
                "quality_score":    rev.get("quality_score"),
                "claims_supported": rev.get("claims_supported"),
            }).execute()

        logger.info(f"[persistence] saved case {case_id} ({status})")
        return True
    except Exception as exc:
        logger.warning(f"[persistence] could not save case: {exc}")
        return False


def persist_decision(case_id: str, decision: str, notes: str | None = None) -> bool:
    """Record a human decision and mark the case closed."""
    try:
        db = client()
        db.table("human_decisions").insert({
            "case_id": case_id, "decision": decision, "notes": notes,
        }).execute()
        db.table("cases").update(
            {"status": "closed", "updated_at": _now()}
        ).eq("case_id", case_id).execute()
        return True
    except Exception as exc:
        logger.warning(f"[persistence] could not save decision: {exc}")
        return False


# ---- long-term memory: a customer's history across past investigations ----
def get_customer_history(customer_id: str, exclude_case_id: str = "") -> dict:
    """Return prior cases + human decisions for a customer (excluding the case
    currently being investigated). Best-effort -- returns empty on any failure."""
    try:
        db = client()
        cases = (db.table("cases").select("*")
                 .eq("customer_id", customer_id).execute().data or [])
        cases = [c for c in cases if c.get("case_id") != exclude_case_id]
        case_ids = [c["case_id"] for c in cases]
        decisions = []
        if case_ids:
            decisions = (db.table("human_decisions").select("*")
                         .in_("case_id", case_ids).execute().data or [])
        return {"cases": cases, "decisions": decisions}
    except Exception as exc:
        logger.warning(f"[persistence] could not load customer history: {exc}")
        return {"cases": [], "decisions": []}


# ---- read-back helpers (for the API / case history) ----
def list_cases(limit: int = 50) -> list[dict]:
    try:
        res = (client().table("cases").select("*")
               .order("updated_at", desc=True).limit(limit).execute())
        return res.data
    except Exception as exc:
        logger.warning(f"[persistence] could not list cases: {exc}")
        return []


def get_case_events(case_id: str) -> list[dict]:
    try:
        res = (client().table("case_events").select("*")
               .eq("case_id", case_id).order("id").execute())
        return res.data
    except Exception as exc:
        logger.warning(f"[persistence] could not get events: {exc}")
        return []
