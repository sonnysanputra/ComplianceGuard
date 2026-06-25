# CompliGuard AI

**A multi-agent AML compliance investigation system.** It turns a raw suspicious-activity alert into a fully investigated, explainable, **traceable** case — with a drafted Suspicious Activity Report (SAR) — in about a minute, while keeping a human analyst in control of the final decision.

Built with **LangGraph** orchestration, a **local Qwen** LLM (via Ollama), **RAG with cross-encoder reranking** (ChromaDB), tool-calling into **Supabase**, relationship-graph network analysis, long- and short-term **memory**, and a **FastAPI** backend with live streaming. Runs entirely on a local model — no per-token API bills, and customer data never leaves the environment.

> **16 specialized agents across 6 stages (8 running in parallel)** on a hybrid *deterministic-rules + local-LLM* architecture. Every decision is traceable to its evidence, the rules that fired, the policies cited, and the human who approved it.

---

## The problem

Bank compliance teams receive hundreds of suspicious-activity alerts daily. Each one requires an analyst to manually pull transaction history, cross-reference the customer's KYC profile, screen watchlists and adverse media, look up internal policy, judge the risk, and write a SAR. It's slow, repetitive, and inconsistent between analysts — and most alerts turn out to be false positives.

**CompliGuard AI automates the investigation** and hands the analyst a finished, evidence-backed draft to approve — it never files anything automatically.

---

## Architecture

A LangGraph pipeline runs a case through **6 stages**. Stage 2 runs **8 agents in parallel**; a **fail-safe router** in Stage 4 decides what happens next.

### The 6 stages at a glance

| Stage | What happens | Agents | Output |
|-------|--------------|--------|--------|
| **1 · Intake & Triage** | Classify the alert, assign priority, **grade data quality** | Alert Intake, Data Quality Gate | typed + prioritized alert — or **halt** if data is missing |
| **2 · Parallel Investigation** | 8 agents gather signals **simultaneously** | Transaction Analysis, Timeline, Relationship Graph, KYC, Watchlist, Adverse Media, Policy RAG, Memory | findings + structured **evidence** |
| **3 · Risk Scoring** | Deterministic rules **⊕** Qwen judgment | Risk Scoring | score, **factor breakdown**, calibrated confidence, **priority + SLA** |
| **4 · Disposition** | A **fail-safe router** picks the path | False-Positive Review, Auto-Clearance | auto-close · FP review · manual review · SAR |
| **5 · Reporting** | Draft + validate the report | SAR Drafting, Compliance Review | 12-section **SAR package** |
| **6 · Human Approval** | An analyst makes the final call | Human Approval | **approved SAR + full audit trail** |

### Flow

```mermaid
flowchart TD
    A([Suspicious Activity Alert]) --> AI

    subgraph S1["STAGE 1 · Intake and Triage"]
        AI["Alert Intake<br/><i>type · severity · P1–P4</i>"] --> DQ{"Data Quality Gate<br/><i>GOOD · PARTIAL · POOR · CRITICAL</i>"}
    end
    DQ -->|POOR / CRITICAL| NMI([Needs More Information])

    subgraph S2["STAGE 2 · Parallel Investigation — 8 agents at once"]
        INV["Transaction Analysis · Timeline · Relationship Graph · KYC Profile<br/>Watchlist · Adverse Media · Policy RAG · Memory"]
    end
    DQ -->|GOOD / PARTIAL| INV

    subgraph S3["STAGE 3 · Risk Scoring"]
        RS["rules ⊕ Qwen<br/><i>factors+evidence · confidence · priority+SLA</i>"]
    end
    INV --> RS

    subgraph S4["STAGE 4 · Disposition (fail-safe router)"]
        R{route}
    end
    RS --> R
    R -->|clean low risk| AC([Auto-close + clearance note])
    R -->|sub-threshold flagged| FP["False-Positive Review"]
    FP -->|cleared| AC

    subgraph S5["STAGE 5 · Reporting"]
        SAR["SAR Drafting"] --> CR["Compliance Review"]
    end
    R -->|high risk| SAR

    subgraph S6["STAGE 6 · Human Approval"]
        H(["⏸ approve · reject · edit · request more info"])
    end
    CR --> H
    FP -->|needs human| H
    R -->|tool failure · watchlist match · degraded data| H
    H -->|request more info| INV
    H -->|decided| DONE([Approved SAR + audit trail])
```

## Agent pipeline — 16 agents across the 6 stages

| # | Agent | Stage | Responsibility |
|---|-------|-------|----------------|
| 1 | **Alert Intake** | 1 · Intake & Triage | Classifies alert type/severity, assigns a provisional **P1–P4** priority, extracts entities, routes |
| 2 | **Data Quality Gate** | 1 · Intake & Triage | Grades data **GOOD / PARTIAL / POOR / CRITICAL_MISSING** with a score; halts un-investigable cases, forces manual review on degraded data |
| 3 | **Transaction Analysis** | 2 · Investigation | Detects the ML **typology** (structuring, mule, layering, overseas, volume spike) + computes the **account behaviour baseline** |
| 4 | **Transaction Timeline** | 2 · Investigation | Reconstructs a **chronological, annotated** event timeline with per-event risk notes |
| 5 | **Relationship Graph** | 2 · Investigation | Builds the **money-flow graph** — fan-out, rapid forwarding, common collector, circular flow (layering / mule network signatures) |
| 6 | **KYC Profile** | 2 · Investigation | **5 consistency checks** (income, occupation, account age, risk, history) + triggers **EDD** |
| 7 | **Watchlist Screening** | 2 · Investigation | Fuzzy-screens **both customer and recipient** against sanctions / PEP / blacklist / scam lists |
| 8 | **Adverse Media** | 2 · Investigation | Negative-news screening (fraud, investigations, enforcement) — catches entities before they're formally listed |
| 9 | **Policy RAG** | 2 · Investigation | Retrieves policies via **vector recall + cross-encoder rerank** over **heading-chunked** docs; returns scored, section-level **citations** |
| 10 | **Memory Agent** | 2 · Investigation | **Long-term memory** — prior cases/escalations, repeat recipients, and **learns from analyst false-positive feedback** |
| 11 | **Risk Scoring** | 3 · Scoring | Blends a **rule baseline** with an independent **Qwen assessment**; emits a **factor breakdown referencing evidence by ID**, a **calibrated confidence**, and a risk-aware **priority + SLA** |
| 12 | **False-Positive Review** | 4 · Disposition | Structured FP workflow — clears benign cases (known recipient, invoice, clear purpose) or refers sanctions name-matches to a human |
| 13 | **Auto-Clearance** | 4 · Disposition | Emits a professional **clearance note** (reason + evidence + recommended action) instead of silently ending |
| 14 | **SAR Drafting** | 5 · Reporting | Generates a structured **12-section regulator-style SAR package** (JSON → Markdown / PDF / DOCX) |
| 15 | **Compliance Review** | 5 · Reporting | Validates **every claim is evidence-backed**; scores completeness + quality |
| 16 | **Human Approval** | 6 · Approval | Structured decision: **approve / reject / edit / request_more_info**, SAR edits, risk overrides, and **feedback tags** for learning |

> Every agent extends `BaseAgent` and emits an **evidence-backed audit rationale** (not raw chain-of-thought), a **confidence score**, **model-governance metadata** (model, prompt, ruleset, policy version), and an agent-to-agent (A2A) status message.

### Design principles

- **Hybrid, not pure-LLM** — deterministic rules/graph/screening compute facts and provide an auditable safety floor; the LLM reasons, judges, and explains. 6 of 16 agents use no LLM at all (recorded as `model_name: null`).
- **Traceable** — every risk factor references **evidence by ID**, and each `EvidenceItem` points to the exact source (a transaction, a profile field, a watchlist entry). One hop from any score back to the raw fact.
- **Fail-safe** — incomplete data → request more info; a failed tool, a watchlist match, or degraded data → manual review (never a SAR on bad data); a human always makes the final call.
- **Calibrated, not self-reported** — confidence is derived from objective signals (data quality, policy found, tool failures, evidence strength), not "the LLM says 87%".
- **Cost-aware** — math, name matching, and graph analysis are plain Python; the LLM is used only where reasoning adds value ($0 on a local model).

---

## Key features

- **16-agent orchestration** (LangGraph) with **8 parallel** investigation agents and **fail-safe conditional routing**
- **Relationship-graph network analysis** — layering / money-mule detection (fan-out, forwarding chains, common collectors, circular flow) with a graph risk score
- **Account behaviour baseline** — scores deviation from the customer's *own* normal (amount spikes, new countries, off-hours, dormant-account reactivation)
- **Adverse-media screening** + multi-list **watchlist** screening (sanctions / PEP / blacklist)
- **Real RAG** — heading-aware chunking + cross-encoder reranking, with section-level **policy citations**; upload your own `.md`/`.pdf` policies and the system **auto-re-indexes**
- **Economic-purpose & source-of-funds** awareness (per SC guidance on clarifying unusual transactions)
- **Structured evidence layer** — every claim is a traceable `EvidenceItem`; risk factors reference evidence IDs
- **Calibrated confidence**, **risk-aware priority + SLA deadlines**, and a graded **data-quality severity**
- **Case status lifecycle** — an enforced state machine (`NEW → … → APPROVED_FOR_STR_REVIEW`) that rejects impossible transitions
- **False-positive workflow** + **auto-close clearance notes** (the system never silently closes a case)
- **Analyst feedback learning** — overrides + corrected typologies lower confidence on similar future cases
- **Model governance** — every output records model / prompt / ruleset / policy version for reproducibility
- **Human-in-the-loop** — structured decisions, SAR edits, risk overrides, bounded re-investigation
- **Full audit trail in Supabase** — cases, evidence, rule hits, policy citations, status history, SAR drafts, decisions (survives restarts); `GET /case/{id}/trace` returns the whole chain
- **12-section regulator-style SAR** exported to **PDF / DOCX / Markdown**
- **Live progress streaming** (SSE) so the UI shows each agent completing in real time
- **Evaluation suite** — golden AML scenarios scoring typology / routing / retrieval / FP-clearance / SAR-completeness, plus **107 offline unit tests**

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph (StateGraph, parallel fan-out, `interrupt()` HITL, checkpointer) |
| LLM | Qwen 2.5 (local, via Ollama) — OpenAI-compatible API |
| Embeddings | nomic-embed-text (Ollama) |
| Vector DB / RAG | ChromaDB + `ms-marco-MiniLM` cross-encoder reranker |
| Relational DB / audit | Supabase (Postgres) |
| Watchlist / name matching | rapidfuzz |
| API | FastAPI + Uvicorn (REST + SSE streaming) |
| Document export | fpdf2 (PDF), python-docx (DOCX), PyMuPDF (policy PDF ingest) |
| Tests / evals | pytest + golden-case eval suite |

---

## Repository structure

```
backend/
├── main.py                 # CLI runner
├── server.py               # FastAPI server entry point
├── schema.sql              # Supabase source tables + seed data
├── schema_cases.sql        # Supabase audit/persistence tables
├── requirements.txt
├── tests/                  # 107 offline unit tests (LLM + DB mocked)
├── evals/                  # golden-case evaluation suite (rules / RAG / SAR quality)
└── app/
    ├── orchestrator.py     # wires the 16 agents into the LangGraph
    ├── api/routes.py       # FastAPI endpoints (REST + SSE + export)
    ├── core/
    │   ├── config.py       # loads .env, all settings
    │   ├── state.py        # the shared CaseState
    │   ├── evidence.py     # structured EvidenceItem + traceability
    │   ├── baseline.py     # account behaviour baseline + deviations
    │   ├── priority.py     # risk-aware priority + SLA
    │   ├── confidence.py   # confidence calibration
    │   ├── case_status.py  # case lifecycle state machine
    │   └── governance.py   # model-governance metadata
    ├── rules/              # AML rule engine (yaml-driven) + country-risk register
    ├── agents/             # one file per agent + base.py (BaseAgent)
    ├── services/           # llm.py (Qwen), persistence.py, sar_render.py
    ├── tools/
    │   ├── db.py           # Supabase queries
    │   ├── rag.py          # ChromaDB + chunking + reranking + citations
    │   ├── adverse_media.py# negative-news screening
    │   ├── graph_analysis.py # money-flow network analysis
    │   └── policies/       # policy documents (.md / .pdf) indexed by RAG
    └── data/scenarios.py   # demo alerts
```

---

## Setup

### Prerequisites
- **Python 3.11+**
- **Ollama** ([ollama.com](https://ollama.com)) — runs the local LLM
- A **Supabase** project (free tier) — the relational database + audit store

### 1. Clone + create a virtual environment
```bash
git clone https://github.com/sonnysanputra/ComplianceGuard.git
cd ComplianceGuard
python -m venv venv
# Windows:  .\venv\Scripts\Activate.ps1
# macOS/Linux:  source venv/bin/activate
```

### 2. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Pull the local models (Ollama)
```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```
> Lower-spec machine? Use `qwen2.5:3b` and set `CHAT_MODEL=qwen2.5:3b` in `.env`.

### 4. Set up Supabase
1. Create a project at [supabase.com](https://supabase.com).
2. In the **SQL Editor**, run [`backend/schema.sql`](backend/schema.sql) (source data) **and** [`backend/schema_cases.sql`](backend/schema_cases.sql) (audit/persistence tables). Both are idempotent — safe to re-run.
3. From **Settings → API**, copy the **Project URL** and the **Secret** key.

### 5. Configure environment
Create `backend/.env`:
```
OLLAMA_BASE_URL=http://localhost:11434/v1
CHAT_MODEL=qwen2.5:7b
EMBED_MODEL=nomic-embed-text
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_KEY=sb_secret_...
```
> `.env` is gitignored — never commit it.

---

## Running

Make sure Ollama is running and your venv is active. From `backend/`:

### CLI (interactive)
```bash
python main.py
```
Pick a demo case; it runs the full investigation, prints findings + risk breakdown + priority/SLA + confidence + SAR draft, and pauses for your decision.

### API server
```bash
python server.py
```
Open **http://localhost:8000/docs**. Check **`GET /health/ready`** first — it confirms Ollama + Supabase are reachable.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` · `/health/ready` | liveness · dependency check |
| GET | `/scenarios` | list demo alerts |
| POST | `/investigate` · `/investigate/stream` | run a case (blocking · **streaming SSE**) |
| GET | `/cases` · `/case/{id}` | list cases · full case state |
| GET | `/case/{id}/status` · `/audit` · `/sar` | status poll · audit timeline · SAR text |
| GET | `/case/{id}/timeline` · `/evidence` · `/trace` | annotated timeline · evidence pool · **full audit chain** |
| POST | `/case/{id}/decision` | approve / reject / edit / request_more_info (+ feedback) |
| POST | `/case/{id}/rerun-agent/{name}` | re-run a single agent |
| POST | `/case/{id}/export-sar?format=pdf\|docx\|markdown` | download the SAR report |
| GET/POST/DELETE | `/policies` · `/policies/upload` · `/policies/reindex` | manage policy docs (auto re-index) |
| GET | `/rules` · `/country-risk` · `/watchlist` · `/case-statuses` | configuration + lifecycle |

### Tests + evals
```bash
pytest                       # 107 offline unit tests (LLM + DB mocked), ~6s
python evals/run_all.py      # golden AML scenarios: typology / routing / RAG / SAR
```

---

## Demo scenarios

| Case | Typology / situation | Outcome |
|------|----------------------|---------|
| AML-2026-001 | Structuring (sub-threshold, overseas) | High → SAR |
| AML-2026-002 | Money mule (large in → forwarded out) | Critical → SAR + EDD |
| AML-2026-003 | Layering / dispersion | Elevated → SAR (with **money-flow graph**) |
| AML-2026-004 | False positive (known supplier) | Low → auto-closed |
| AML-2026-005 | Repeat offender (run after 001) | **Long-term memory boosts risk** |
| AML-2026-006 | Unknown customer, no data | **NEEDS_MORE_INFORMATION** (gate halts it) |
| AML-2026-007 | Documented supplier payment, volume-flagged | **False-positive review → auto-close with clearance note** |

---

## Notes

- First run downloads the cross-encoder reranker (~80MB) and builds the ChromaDB policy store from `app/tools/policies/` automatically; it re-indexes whenever a policy file changes or one is uploaded.
- Generated artifacts (`backend/chroma_db/`, `venv/`) and secrets (`.env`) are gitignored and rebuilt/supplied on demand.
- On a CPU-only machine, a full case takes ~1–2 minutes on the 7B model; the 3B model is faster.
- Persistence and the audit trail are **best-effort** — if the Supabase audit tables aren't created, investigations still run (with a logged warning).
