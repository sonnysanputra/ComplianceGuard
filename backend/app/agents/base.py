import time
import re
import json
from abc import ABC, abstractmethod

from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.llm import chat
from app.core.state import stamp

_JSON_SUFFIX = "\n\nRespond with ONLY a valid JSON object. No markdown, no extra text."

# Shared confidence rubric -- included in agent prompts so scores are calibrated
# the same way everywhere (instead of the model guessing what a score means).
CONFIDENCE_RUBRIC = (
    "Confidence rubric (0-100): 90-100 = directly supported by the stated facts; "
    "70-89 = strong inference; 40-69 = weak or partial signal; "
    "below 40 = uncertain guess."
)


# Injected before an agent's own system prompt when it uses self.reason().
# A compliance product exposes a concise, evidence-backed rationale -- NOT raw
# "chain-of-thought" or hidden reasoning.
_RATIONALE_PREFIX = """Provide a concise audit rationale based only on the evidence.
Then give a confidence score. Do not include hidden reasoning or unsupported assumptions.

Format your answer exactly like this:
<rationale>
[your concise, evidence-based rationale]
</rationale>
Confidence: [0-100]

"""


class BaseAgent(ABC):
    name: str = "base_agent"     # machine id, used in traces/messages
    label: str = "Base Agent"    # human-readable, used in the audit timeline
    prompt_version: str = None   # governance: prompt version (defaults to <name>_v1)
    uses_llm: bool = True        # governance: False for purely deterministic agents

    # ── Subclasses implement this ─────────────────────────────────────────
    @abstractmethod
    def run(self, state: dict) -> dict:
        """Do the work. Return ONLY the state keys this agent writes.
        Should include a 'audit_rationales' entry built with self.trace(...)."""

    # ── LangGraph node entry point (wraps run with timing + a2a + retry) ──
    def __call__(self, state: dict) -> dict:
        start = time.time()
        try:
            updates = self._run_with_retry(state)
        except Exception as exc:
            duration = int((time.time() - start) * 1000)
            return {
                "audit_rationales": [self.trace(f"Agent failed: {exc}", 0.0)],
                "a2a_messages": [{"from": self.name, "status": "error",
                                  "error": str(exc), "duration_ms": duration}],
                "errors": [{"agent": self.name, "error": str(exc)}],   # forces manual review
                "audit": stamp(f"{self.label} ERROR: {exc}"),
            }

        duration = int((time.time() - start) * 1000)

        # stamp duration onto this agent's trace, and emit an A2A message
        confidence = None
        if updates.get("audit_rationales"):
            updates["audit_rationales"][-1]["duration_ms"] = duration
            confidence = updates["audit_rationales"][-1].get("confidence")

        updates.setdefault("a2a_messages", [])
        updates["a2a_messages"].append({
            "from": self.name, "status": "ok",
            "confidence": confidence, "duration_ms": duration,
        })
        return updates

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=1, max=6),
           reraise=True)
    def _run_with_retry(self, state: dict) -> dict:
        return self.run(state)

    # ── Helpers for subclasses ────────────────────────────────────────────
    def llm(self, prompt: str, system: str | None = None) -> str:
        """Plain text generation (e.g. SAR drafting)."""
        return chat(prompt, system=system)

    def reason(self, system: str, prompt: str) -> tuple[str, float]:
        """Single rationale call. Returns (rationale_text, confidence 0..1)."""
        raw = chat(prompt, system=_RATIONALE_PREFIX + (system or ""))
        return self._parse_rationale(raw)

    def think(self, system: str, prompt: str) -> dict:
        """LLM call that returns a parsed JSON object (the model's reasoning +
        structured fields). Returns {} on parse failure so callers can fall back
        to deterministic logic. This is how Qwen does real detection/judgment."""
        raw = chat(prompt, system=(system or "") + _JSON_SUFFIX)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Extract a JSON object from a model response, tolerating code fences."""
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)   # grab the JSON body
        if match:
            raw = match.group(0)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}

    def trace(self, rationale: str, confidence: float,
              evidence: list | None = None, output: dict | None = None) -> dict:
        """Build an audit-rationale entry: a concise, evidence-backed rationale, a
        confidence score, and model-governance metadata (what produced this output)."""
        from app.core.governance import governance
        gov = governance(self.prompt_version or f"{self.name}_v1", self.uses_llm)
        return {
            "agent": self.name,
            "rationale": rationale,
            "confidence": round(float(confidence), 2),
            "evidence": evidence or [],
            "output": output or {},
            "duration_ms": 0,   # filled in by __call__
            **gov,              # model_name, prompt_version, ruleset_version, policy_version
        }

    @staticmethod
    def _parse_rationale(raw: str) -> tuple[str, float]:
        """Pull the <rationale> block and a 'Confidence: NN' score from a response."""
        rationale = raw.strip()
        m = re.search(r"<rationale>(.*?)</rationale>", raw, re.DOTALL | re.IGNORECASE)
        if m:
            rationale = m.group(1).strip()

        confidence = 0.8  # sensible default if the model omits it
        cm = re.search(r"confidence:\s*(\d+)", raw, re.IGNORECASE)
        if cm:
            confidence = min(int(cm.group(1)) / 100.0, 1.0)
        return rationale, confidence
