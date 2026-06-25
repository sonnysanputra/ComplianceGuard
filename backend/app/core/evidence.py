"""
Structured evidence -- the traceability backbone of the investigation.

Every claim an agent makes should be backed by an EvidenceItem that points to the
exact source (a transaction, a profile field, a watchlist entry, a policy, a memory
record, an analyst note). Risk factors then reference evidence by ID instead of by
free text, so an auditor can follow any score back to the raw facts.

Each agent uses its own EvidenceCollector (with a readable per-source prefix) and
returns `evidence` in its state update; the graph accumulates them into one pool.
Risk scoring resolves its factors against that shared pool (see `index_evidence`),
reusing the IDs upstream agents already minted rather than duplicating them.
"""

from typing import Literal, Union

from pydantic import BaseModel

SourceType = Literal["transaction", "customer_profile", "watchlist",
                     "adverse_media", "policy", "memory", "analyst_note", "rule"]

# readable ID prefix per source type, e.g. EV-TXN-001
_PREFIX = {
    "transaction": "TXN",
    "customer_profile": "CUST",
    "watchlist": "WL",
    "adverse_media": "AM",
    "policy": "POL",
    "memory": "MEM",
    "analyst_note": "NOTE",
    "rule": "RULE",
}


class EvidenceItem(BaseModel):
    evidence_id: str
    source_type: SourceType
    source_id: str
    field: str
    value: Union[str, int, float, bool]
    description: str


def _key(source_type: str, source_id, field: str) -> tuple:
    return (source_type, str(source_id), field)


class EvidenceCollector:
    """Mints stable, readable evidence IDs (EV-<PREFIX>-NNN) and dedupes by
    (source_type, source_id, field) so the same fact gets one ID.

    `prefix` pins the ID namespace for this collector. Agents that emit a single
    source type can rely on the per-source-type default; agents that emit a type
    others also emit (e.g. transactions) MUST pass a unique prefix so IDs stay
    globally unique across the parallel fan-out (TL, RF, ...)."""

    def __init__(self, prefix: str | None = None):
        self._items: dict[tuple, dict] = {}
        self._counts: dict[str, int] = {}
        self._prefix = prefix

    def add(self, source_type: str, source_id, field: str, value, description: str) -> str:
        key = _key(source_type, source_id, field)
        if key in self._items:
            return self._items[key]["evidence_id"]
        prefix = self._prefix or _PREFIX.get(source_type, "EV")
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        eid = f"EV-{prefix}-{self._counts[prefix]:03d}"
        self._items[key] = EvidenceItem(
            evidence_id=eid, source_type=source_type, source_id=str(source_id),
            field=field, value=value, description=description).model_dump()
        return eid

    @property
    def items(self) -> list[dict]:
        return list(self._items.values())


def index_evidence(pool: list[dict]) -> dict[tuple, str]:
    """Build a {(source_type, source_id, field): evidence_id} lookup from an
    existing evidence pool, so downstream agents can reference rather than re-mint."""
    return {_key(e["source_type"], e["source_id"], e["field"]): e["evidence_id"]
            for e in (pool or [])}
