"""
Model governance.

Every AI output records exactly what produced it -- the model, the prompt
version, the active ruleset version, and the policy-corpus version -- so any
decision can be reproduced and audited later. Versions are cached (they only
change on reload/reindex) and resolved lazily + best-effort so governance
metadata never breaks an agent.
"""

_cache: dict = {}


def model_name() -> str | None:
    if "model" not in _cache:
        try:
            from app.core.config import CHAT_MODEL
            _cache["model"] = CHAT_MODEL
        except Exception:
            _cache["model"] = None
    return _cache["model"]


def ruleset_version() -> str | None:
    if "ruleset" not in _cache:
        try:
            from app.rules.rule_engine import ruleset_version as _rv
            _cache["ruleset"] = _rv()
        except Exception:
            _cache["ruleset"] = None
    return _cache["ruleset"]


def policy_version() -> str | None:
    if "policy" not in _cache:
        try:
            from app.tools.rag import policy_version as _pv
            _cache["policy"] = _pv()
        except Exception:
            _cache["policy"] = None
    return _cache["policy"]


def governance(prompt_version: str, uses_llm: bool = True) -> dict:
    """Governance metadata stamped onto an agent output."""
    return {
        "model_name": model_name() if uses_llm else None,
        "prompt_version": prompt_version,
        "ruleset_version": ruleset_version(),
        "policy_version": policy_version(),
    }


def reset_cache() -> None:
    """Drop cached versions (call after a rules reload / policy reindex)."""
    _cache.clear()
