"""
Data models for the AML rule engine.

A TriggeredRule is a single deterministic AML rule that fired, with the points
it contributes, its severity, and the concrete evidence. A RuleResult bundles
all fired rules, the total rule score, and the detected typology.
"""

from dataclasses import dataclass, asdict, field


@dataclass
class TriggeredRule:
    rule_id: str
    name: str
    points: int
    severity: str          # CRITICAL | HIGH | MEDIUM | LOW | INFO
    evidence: str          # human-readable summary (kept for display / back-compat)
    source: str = "Internal AML typology rule"
    # structured evidence inputs: each is {source_type, source_id, field, value, description}
    # (the risk-scoring agent resolves these to evidence_ids against the shared pool)
    evidence_items: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleResult:
    triggered_rules: list = field(default_factory=list)
    total_rule_score: int = 0
    typology: str = "none"
    flags: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "triggered_rules": [r.to_dict() for r in self.triggered_rules],
            "total_rule_score": self.total_rule_score,
            "typology": self.typology,
            "flags": self.flags,
        }
