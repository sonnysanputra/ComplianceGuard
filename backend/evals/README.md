# Evaluation suite

Beyond the pytest unit tests, this suite evaluates the system **end-to-end against
golden AML scenarios** — one per typology — so we can make accuracy claims, not
just "it runs".

```
evals/
├── golden_cases.json        # golden cases with embedded data + expected outcomes
├── _common.py               # runs the deterministic pipeline for a case (offline)
├── evaluate_rules.py        # typology / risk-score / routing / FP-clearance accuracy
├── evaluate_rag.py          # policy-retrieval accuracy (recall@k) — needs Ollama
├── evaluate_sar_quality.py  # SAR structural completeness (12 sections present)
└── run_all.py               # runs all three, prints a summary, gates CI
```

## Run

```bash
python evals/run_all.py            # everything
python evals/evaluate_rules.py     # offline (no LLM / DB)
python evals/evaluate_sar_quality.py
python evals/evaluate_rag.py       # requires Ollama (embeddings); skipped if down
```

## Metrics

| Metric | Script |
|---|---|
| `typology_accuracy` | evaluate_rules |
| `risk_score_within_expected_range` | evaluate_rules |
| `routing_accuracy` | evaluate_rules |
| `false_positive_clearance_accuracy` | evaluate_rules |
| `policy_retrieval_accuracy` (recall@k) | evaluate_rag |
| `SAR_required_sections_present` | evaluate_sar_quality |

## Golden case shape

```json
{
  "case_id": "AML-STRUCT-GOLD-001",
  "customer": { ... }, "transactions": [ ... ], "alert": { ... },
  "expected_typology": "structuring",
  "expected_min_score": 60,
  "expected_policy_ids": ["AML-TYP-STRUCT-001", "MY-AML-STR-001"],
  "expected_route": "SAR_DRAFTED",
  "expected_fp_clearance": true
}
```

The rule/detection and SAR-structure evals are **deterministic and offline** (the
LLM is stubbed, data is embedded in the JSON), so they are reproducible and can
run in CI. RAG retrieval needs the embedding model and is skipped if it is
unavailable.
