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
from app.core.case_status import is_valid_transition, status_for_decision, CaseStatus
from app.core.priority import sla_due_at

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

        # capture the prior status + creation time (so the SLA stays anchored)
        prev = (db.table("cases").select("status, created_at")
                .eq("case_id", case_id).execute().data or [])
        old_status = prev[0]["status"] if prev else None
        created = prev[0].get("created_at") if prev else None

        # risk-aware priority (set by risk scoring); fall back to intake's provisional
        priority = state.get("priority") or tri.get("priority")

        # 1) the case row (upsert on case_id)
        db.table("cases").upsert({
            "case_id":         case_id,
            "customer_id":     alert.get("customer_id"),
            "alert_reason":    alert.get("reason"),
            "recipient":       alert.get("recipient"),
            "alert_type":      tri.get("alert_type"),
            "typology":        tf.get("typology"),
            "priority":        priority,
            "priority_reason": state.get("priority_reason"),
            "sla_due_at":      sla_due_at(priority, created),
            "status":          status,
            "risk_score":      state.get("risk_score"),
            "rule_score":      state.get("rule_score"),
            "ai_score":        state.get("ai_score"),
            "risk_level":      state.get("risk_level"),
            "recommendation":  state.get("recommendation"),
            "updated_at":      _now(),
        }).execute()

        # log the status transition (append-only history), flagging any that
        # break the lifecycle rules so impossible states are caught
        if status != old_status:
            valid = is_valid_transition(old_status, status)
            if not valid:
                logger.warning(f"[persistence] unexpected status transition "
                               f"{old_status} -> {status} for case {case_id}")
            db.table("case_status_history").insert({
                "case_id": case_id, "old_status": old_status, "new_status": status,
                "changed_by": "system",
                "reason": ("automated case transition" if valid
                           else f"automated transition (unexpected from {old_status})"),
            }).execute()

        # clear child rows so a re-run doesn't duplicate them
        # (case_status_history is append-only -- never cleared)
        for tbl in ("case_events", "agent_outputs", "risk_assessments",
                    "sar_drafts", "watchlist_matches", "evidence_items",
                    "rule_hits", "policy_citations"):
            db.table(tbl).delete().eq("case_id", case_id).execute()

        # structured evidence pool -- every claim is traceable to one of these
        evidence = state.get("evidence", [])
        if evidence:
            db.table("evidence_items").insert([{
                "evidence_id": e.get("evidence_id"), "case_id": case_id,
                "source_type": e.get("source_type"), "source_id": e.get("source_id"),
                "field": e.get("field"), "value": e.get("value"),
                "description": e.get("description"),
            } for e in evidence]).execute()

        # triggered AML rules + the evidence IDs each one relied on
        factors = state.get("risk_factors", [])
        if factors:
            db.table("rule_hits").insert([{
                "case_id": case_id, "rule_id": f.get("rule_id"),
                "rule_name": f.get("factor") or f.get("name"),
                "typology": tf.get("typology"), "severity": f.get("severity"),
                "points": f.get("points"), "evidence_ids": f.get("evidence_ids") or [],
            } for f in factors]).execute()

        # policy citations retrieved + reranked by the RAG layer
        policies = state.get("retrieved_policies", [])
        if policies:
            db.table("policy_citations").insert([{
                "case_id": case_id, "policy_id": p.get("policy_id"),
                "title": p.get("title"), "section": p.get("section"),
                "category": p.get("category"),
                "content_excerpt": (p.get("excerpt") or p.get("content") or "")[:500] or None,
                "retrieval_score": p.get("retrieval_score"),
                "rerank_score": p.get("rerank_score"),
            } for p in policies]).execute()

        # watchlist screening matches
        wl_matches = (state.get("watchlist_findings") or {}).get("all_matches", [])
        if wl_matches:
            db.table("watchlist_matches").insert([{
                "case_id": case_id, "searched_name": m.get("searched_name"),
                "matched_entity_id": m.get("matched_entity_id"),
                "matched_entity": m.get("matched_entity"),
                "list_type": m.get("list_type"), "match_score": m.get("score"),
                "match_type": m.get("match_type"),
            } for m in wl_matches]).execute()

        # 2) events + 3) structured outputs, both from the audit rationales
        events, outputs = [], []
        for t in state.get("audit_rationales", []):
            events.append({
                "case_id":    case_id,
                "agent_name": t.get("agent"),
                "event_type": "rationale",
                "message":    (t.get("rationale") or "")[:1000],
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
                "factors":     state.get("risk_factors") or [],
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


def persist_decision(case_id: str, decision: str, analyst_id: str | None = None,
                     notes: str | None = None, final_risk_level: str | None = None,
                     analyst_agrees_with_ai: bool | None = None,
                     corrected_typology: str | None = None,
                     corrected_reason: str | None = None,
                     feedback_tags: list | None = None) -> bool:
    """Record a structured human decision (incl. analyst feedback for learning)
    and update the case status."""
    try:
        db = client()
        db.table("human_decisions").insert({
            "case_id": case_id, "decision": decision, "analyst_id": analyst_id,
            "notes": notes, "final_risk_level": final_risk_level,
            "analyst_agrees_with_ai": analyst_agrees_with_ai,
            "corrected_typology": corrected_typology,
            "corrected_reason": corrected_reason,
            "feedback_tags": feedback_tags,
        }).execute()
        # map the decision onto the lifecycle (approve -> APPROVED_FOR_STR_REVIEW, etc.)
        status = status_for_decision(decision)
        prev = (db.table("cases").select("status")
                .eq("case_id", case_id).execute().data or [])
        old_status = prev[0]["status"] if prev else None
        db.table("cases").update(
            {"status": status, "updated_at": _now()}
        ).eq("case_id", case_id).execute()
        # record the human-driven transition
        if status != old_status:
            if not is_valid_transition(old_status, status):
                logger.warning(f"[persistence] unexpected status transition "
                               f"{old_status} -> {status} for case {case_id}")
            db.table("case_status_history").insert({
                "case_id": case_id, "old_status": old_status, "new_status": status,
                "changed_by": analyst_id or "analyst",
                "reason": f"Analyst decision: {decision}" + (f" - {notes}" if notes else ""),
            }).execute()
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


def _read_case_rows(table: str, case_id: str, order: str = "id") -> list[dict]:
    """Generic best-effort read of a case's child rows from an audit table."""
    try:
        return (client().table(table).select("*")
                .eq("case_id", case_id).order(order).execute().data or [])
    except Exception as exc:
        logger.warning(f"[persistence] could not read {table}: {exc}")
        return []


def get_case_evidence(case_id: str) -> list[dict]:
    return _read_case_rows("evidence_items", case_id, order="evidence_id")


def get_case_rule_hits(case_id: str) -> list[dict]:
    return _read_case_rows("rule_hits", case_id)


def get_case_policy_citations(case_id: str) -> list[dict]:
    return _read_case_rows("policy_citations", case_id)


def get_case_status_history(case_id: str) -> list[dict]:
    return _read_case_rows("case_status_history", case_id)


def get_case_trace(case_id: str) -> dict:
    """The full audit chain for a case: evidence -> rules -> policy -> status history.
    Backs the claim that every decision is traceable end to end."""
    return {
        "evidence": get_case_evidence(case_id),
        "rule_hits": get_case_rule_hits(case_id),
        "policy_citations": get_case_policy_citations(case_id),
        "status_history": get_case_status_history(case_id),
        "decisions": _read_case_rows("human_decisions", case_id),
    }


def get_case_sar(case_id: str) -> str | None:
    """Return the latest persisted SAR draft for a case (if any)."""
    try:
        res = (client().table("sar_drafts").select("draft_text")
               .eq("case_id", case_id).order("id", desc=True).limit(1).execute())
        return res.data[0]["draft_text"] if res.data else None
    except Exception as exc:
        logger.warning(f"[persistence] could not get SAR: {exc}")
        return None
