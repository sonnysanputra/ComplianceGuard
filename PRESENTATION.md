# ComplianceGuard AI — Presentation Deck (Full Context)

> **One-liner:** An AI multi-agent copilot that investigates AML alerts end-to-end — ingest → investigate → draft the SAR → human sign-off — running on a **local LLM so customer data never leaves the bank.**
>
> Everything below is grounded in the working prototype (14 agents, 6 stages, 114 passing tests). Numbers labelled *(industry estimate)* or *(illustrative)* are directional, not measured — swap in cited sources before presenting to investors/regulators.

---

## SLIDE 1 — Title

**ComplianceGuard AI**
*The AI compliance analyst that investigates money-laundering alerts — privately, on your own infrastructure.*

- Multi-agent AML investigation copilot
- Built for Malaysian banks, digital banks & fintechs
- [Team name] · [Event / Date]

**Speaker note:** "Every bank in Malaysia is legally required to investigate suspicious transactions and file reports. Today that's slow, manual, and 95% wasted effort. We automate the investigation — without sending a single customer record to the cloud."

---

## SLIDE 2 — Problem Statement

**Compliance teams are drowning in false alarms — and the cost of getting it wrong is enormous.**

- 🌊 **Alert overload** — transaction-monitoring systems flag huge volumes of activity; **~90–95% are false positives** *(industry estimate)*.
- ⏳ **Slow & manual** — each alert can take an analyst **hours** to investigate: pulling transactions, checking KYC, screening watchlists, searching news, writing it up.
- 🧩 **Inconsistent & hard to audit** — outcomes vary by analyst; rationale lives in people's heads; regulators demand a defensible trail.
- 💸 **Expensive & unscalable** — skilled AML analysts are costly and scarce; backlogs grow with transaction volume.
- ⚖️ **Regulatory risk** — global AML penalties run into **billions every year** *(industry estimate)*; in Malaysia, reporting institutions must file STRs to **BNM's FIED** under **AMLA 2001**.
- ☁️ **AI is blocked by privacy** — banks can't send customer data to cloud LLMs (data-residency / secrecy obligations), so most "AI compliance" tools are a non-starter.

**Speaker note:** Land the pain on the analyst (drowning in noise) and on the bank (fines + can't use cloud AI). That last point is the wedge for our solution.

---

## SLIDE 3 — Why Now

- 📈 Surge in transaction volume from **digital banks & e-wallets** (new BNM digital-bank licences) → alert volumes exploding.
- 🔍 Rising regulatory scrutiny on AML effectiveness and SAR quality.
- 🤖 Local/open LLMs (Qwen, Llama) are now **good enough to run on-prem** — privacy-preserving AI is finally viable for banks.
- 🧠 Agentic AI (multi-agent orchestration) matured in the last 18 months.

**Speaker note:** "The technology to do this privately only became practical recently — that's our timing."

---

## SLIDE 4 — Solution

**ComplianceGuard AI — an agentic investigation copilot that does the analyst's legwork in minutes, with a full audit trail, on your own servers.**

For every alert it automatically:
1. **Triages** the alert and checks data quality
2. **Investigates in parallel** — transactions, network graph, KYC, watchlists, adverse media, policy, case history
3. **Scores** the risk (deterministic rules + AI reasoning)
4. **Disposes** — auto-clears genuine false positives, escalates real risk
5. **Drafts a regulator-style SAR** (12 sections, branded PDF/DOCX)
6. **Routes to a human** for the final decision

> Rules **own the decision** (auditable, no hallucinated verdicts). The **LLM explains and reasons** in plain English. Everything is evidence-backed and version-stamped.

**Speaker note:** Emphasise "copilot, not autopilot" — the human approves. That's what makes it safe and sellable to compliance officers.

---

## SLIDE 5 — How It Works (the 6-stage flow)

```
ALERT  ─▶  ① INTAKE        Alert triage · Data-quality gate
            │
            ▼
        ② INVESTIGATION    ┌─ Transaction analysis ─┐
         (8 agents run     ├─ Relationship graph    │
          IN PARALLEL)     ├─ KYC profile           │  all at once,
                           ├─ Watchlist screening    ├─ then merged
                           ├─ Adverse media (live)   │
                           ├─ Policy RAG             │
                           └─ Case memory ───────────┘
            │
            ▼
        ③ SCORING          Risk scoring (rules + AI) · confidence · priority/SLA
            │
            ▼
        ④ DISPOSITION      False-positive review ─▶ Auto-close   (low risk)
            │                                   └─▶ escalate     (high risk)
            ▼
        ⑤ REPORTING        SAR drafting (12-section regulator format)
            │
            ▼
        ⑥ APPROVAL         Human-in-the-loop  ▶  Approve / Edit / Reject
```

**Speaker note:** Walk it left-to-right. Stress the **parallel fan-out** in stage 2 (speed) and the **fail-safe routing** + **human gate** at the end (safety).

---

## SLIDE 6 — Key Features (technical highlights)

- 🧠 **14 specialized agents, 6 stages** — orchestrated with LangGraph (parallel fan-out, conditional routing, human-in-the-loop interrupts).
- 🔒 **Runs on a local LLM (Qwen via Ollama)** — *data never leaves the bank's infrastructure.*
- ⚖️ **Hybrid rules + AI** — deterministic AML rules make the call; the LLM reasons & narrates → **no hallucinated decisions.**
- 🧾 **Evidence layer** — every risk factor links to structured evidence items (traceable claim → source).
- 🏛️ **Model governance** — every output stamped with model / prompt / ruleset / policy version (audit-ready).
- 📚 **Policy RAG** — retrieves & reranks the bank's AML policies (ChromaDB + cross-encoder) to ground decisions in real rules.
- 🌐 **Live adverse-media screening** — real internet news search + grounded LLM review (not hardcoded).
- 🕸️ **Network/graph analysis** — detects layering, smurfing, mule fan-out/fan-in patterns.
- 🔁 **Self-learning false-positive suppression** — once an analyst clears a vendor as benign, similar alerts on *any* customer are auto-recognised (cross-customer learning).
- 📄 **Document & statement ingestion** — upload a PDF/DOCX/CSV **or a scanned bank statement (OCR)**; it auto-extracts the alert, profile & transactions.
- 📑 **Professional SAR output** — branded, regulator-style 12-section PDF & DOCX, downloadable.
- ✅ **114 automated tests + golden-case evaluations.**

**Speaker note:** If short on time, lead with the three that win deals: **local LLM (privacy)**, **hybrid (auditable)**, **end-to-end (ingest→SAR)**.

---

## SLIDE 7 — Feature Spotlight: Real-World Statement Ingestion

**Upload any bank statement — even a scanned one — and the system reads it.**

- Digital PDF/DOCX/CSV → **word-position row reconstruction** + **deterministic running-balance parser** (derives in/out from balance deltas; never drops rows).
- Scanned / photographed statement → **OCR fallback (EasyOCR)** → same parser.
- Proven on a Malaysian (Maybank-style) statement: **14/14 transactions extracted**, including 3 sub-threshold *structuring* transfers — from both the digital and the scanned version.
- LLM reads the prose (alert reason, customer profile); the deterministic parser handles the numbers.

**Speaker note:** This is the "it actually works on messy real inputs" proof point. Demo it live if you can.

---

## SLIDE 8 — Feature Spotlight: Self-Learning Triage

**It gets smarter with every analyst decision.**

- Analyst clears Customer A's payment to "CloudHost Services" as a benign vendor.
- The system distils a **portable suppression pattern**.
- When Customer B later pays the *same* vendor, it's **auto-recognised and down-weighted** — with the original analyst decision cited.
- Result: the same benign vendors stop generating repeat false positives across the whole book.

**Speaker note:** "Most tools re-investigate the same benign merchant 1,000 times. Ours learns once and applies it everywhere."

---

## SLIDE 9 — Technical Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND  — Next.js 16 · React 19 · Tailwind v4                       │
│  Dashboard · Live agent stream · Case workspace · SAR preview ·        │
│  Analytics · Audit logs · Settings · New-investigation / upload        │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  REST + Server-Sent Events (live stream)
┌───────────────────────────────▼──────────────────────────────────────┐
│  API LAYER  — FastAPI (Python)                                         │
│  /investigate/stream · /alerts/extract · /ingest · /case · /export-sar │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
┌───────────────────────────────▼──────────────────────────────────────┐
│  ORCHESTRATION  — LangGraph StateGraph                                 │
│  14 agents · 6 stages · parallel fan-out · fail-safe conditional       │
│  routing · human-in-the-loop interrupt · checkpointer                  │
└──┬───────────────┬────────────────┬───────────────┬──────────────────┘
   │               │                │               │
┌──▼─────────┐ ┌───▼─────────┐ ┌────▼────────┐ ┌────▼───────────────┐
│ LOCAL LLM  │ │   RAG       │ │  DATA        │ │  TOOLS / SERVICES   │
│ Qwen 2.5   │ │ ChromaDB +  │ │ Supabase     │ │ Adverse-media (web) │
│ (Ollama)   │ │ nomic-embed │ │ (Postgres):  │ │ Graph analysis      │
│ — on-prem, │ │ + cross-    │ │ customers,   │ │ Doc/OCR extraction  │
│ no data    │ │ encoder     │ │ txns, cases, │ │ Statement parser    │
│ egress     │ │ reranker    │ │ audit trail  │ │ SAR render (PDF/DOCX)│
└────────────┘ └─────────────┘ └──────────────┘ └─────────────────────┘

         CROSS-CUTTING:  Evidence layer · Model governance (versioning) ·
         Case-status lifecycle · Priority/SLA · Confidence calibration ·
         Behaviour baseline · Self-learning suppression
```

**Tech stack at a glance**
| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind v4 |
| API | FastAPI, Server-Sent Events streaming |
| Orchestration | LangGraph (StateGraph, parallel, interrupts, checkpointing) |
| LLM | Qwen 2.5 (7B) via **Ollama — local/on-prem** |
| RAG | ChromaDB · nomic-embed-text embeddings · cross-encoder reranker |
| Database | Supabase (PostgreSQL) — operational + full audit tables |
| Documents | PyMuPDF, python-docx, EasyOCR (scanned), fpdf2 (reports) |
| Quality | 114 pytest tests + golden-case eval suite |

**Speaker note:** The single most important architectural fact: **the LLM is local.** Draw a box around it. That's the privacy moat.

---

## SLIDE 10 — The Agent Roster (14 agents / 6 stages)

| Stage | Agents | Job |
|---|---|---|
| **1 · Intake** | Alert Intake · Data Quality | Classify the alert; gate on missing data |
| **2 · Investigation** *(parallel)* | Transaction Analysis · Relationship Graph · KYC Profile · Watchlist Screening · Adverse Media · Policy RAG · Case Memory | Gather all evidence at once |
| **3 · Scoring** | Risk Scoring | Blend rule score + AI score → risk level, confidence, priority/SLA |
| **4 · Disposition** | False-Positive Review · Auto-Close | Clear genuine FPs, escalate real risk |
| **5 · Reporting** | SAR Drafting | 12-section regulator-style suspicious-activity report |
| **6 · Approval** | Human Approval | Analyst approves / edits / rejects (human-in-the-loop) |

**Speaker note:** You don't need to name all 14 on the slide — group by stage. Mention that stage-2 agents run *simultaneously*, which is why it's fast.

---

## SLIDE 11 — What Makes Us Different (Moat)

| | Typical AML tooling | **ComplianceGuard AI** |
|---|---|---|
| **AI deployment** | Cloud LLM (blocked by data rules) or none | **Local LLM — zero data egress** |
| **Decision basis** | Black-box score *or* hallucination-prone LLM | **Rules decide, AI explains — auditable** |
| **Scope** | Alert scoring only | **End-to-end: ingest → investigate → SAR → sign-off** |
| **Auditability** | Limited | **Evidence + model/policy version on every output** |
| **Learning** | Static rules | **Cross-customer false-positive learning** |
| **Inputs** | Structured feeds only | **Also reads PDFs & scanned statements (OCR)** |

**Speaker note:** The defensible wedge = **privacy (local) + auditability (hybrid)**. Those two together are hard for cloud-AI incumbents to copy and are exactly what regulated banks require.

---

## SLIDE 12 — Target Market

**Who:** Reporting institutions under Malaysia's AMLA 2001 that must investigate alerts and file STRs to **BNM / FIED**.

- 🎯 **Beachhead:** Malaysian **digital banks, e-wallets, remittance & payment fintechs** — high transaction volume, lean compliance teams, cloud-native, fast to buy.
- 🏦 **Expansion:** Tier-1 & mid-tier **Malaysian banks** (on-prem deployments).
- 🌏 **Scale-out:** **SEA reporting institutions** (Singapore, Indonesia, Philippines, Thailand) — similar FATF-driven regimes.

**Economic buyer:** Head of Compliance / MLRO, Chief Risk Officer.
**Champion:** AML team leads & investigators (they feel the pain daily).

**Why they buy:** cut investigation time & analyst cost, reduce backlog, improve SAR quality & consistency, stay audit-ready — *without breaking data-residency rules.*

**Market sizing (fill with cited figures):**
- TAM — global AML/RegTech software spend *(tens of billions USD, industry estimate)*
- SAM — APAC AML investigation/case-management tooling
- SOM — Malaysian banks + licensed fintechs/e-wallets (a countable, addressable list)

**Speaker note:** Beachhead = fintechs (fast sales cycle, cloud-friendly), then move up to banks (bigger contracts, on-prem). Keep TAM/SAM/SOM honest — investors punish made-up numbers.

---

## SLIDE 13 — Business Model & Pricing *(proposed / illustrative)*

**Model:** B2B SaaS subscription + usage, with a premium **self-hosted / on-prem** tier (enabled by the local-LLM design).

| Tier | For | Deployment | Indicative price *(illustrative)* |
|---|---|---|---|
| **Starter** | Small fintech / e-wallet | Cloud (single-tenant) | ~RM 4–8k / month (capped alert volume) |
| **Growth** | Digital bank / scaling fintech | Cloud or VPC | ~RM 20–40k / month (+ usage over cap) |
| **Enterprise** | Tier-1 / mid-tier bank | **On-prem / self-hosted** | Annual licence (RM 500k+/yr) + deployment & support |

**Add-ons:** implementation & integration, custom typologies/rules, premium support/SLA, regulator-reporting modules.

**Pricing logic:** anchored to **analyst FTE cost saved** — if one analyst investigates *N* alerts/day and we cut investigation time by X%, we price at a fraction of the headcount we displace/augment. Land with a paid pilot, expand by volume & seats.

**Speaker note:** Be explicit these are *proposed* numbers. The real anchor is ROI vs. analyst headcount — present a simple "1 analyst = RM X/yr; we do the work of N at a fraction" slide if asked.

---

## SLIDE 14 — Traction / What's Already Built

- ✅ **Working end-to-end prototype** — 14-agent LangGraph workflow, live-streaming UI, case workspace.
- ✅ **Local-LLM** investigation (Qwen via Ollama) — fully on-prem capable.
- ✅ **RAG over AML policies** (ChromaDB + reranker), live adverse-media search.
- ✅ **Document + scanned-statement ingestion** (OCR) — verified on Malaysian statement formats.
- ✅ **Regulator-style SAR** generation (branded PDF/DOCX).
- ✅ **Self-learning** false-positive suppression.
- ✅ **Full audit trail** (evidence + governance versioning) persisted to Postgres.
- ✅ **114 automated tests + golden-case evals** passing.

**Speaker note:** Frame as "this isn't slideware — it runs." Offer the live demo.

---

## SLIDE 15 — Implementation Roadmap (Technical + Business)

**TECHNICAL**

| Phase | Timeline | Deliverables |
|---|---|---|
| **0 · MVP** *(done)* | — | 14-agent workflow · RAG · SAR · doc/OCR ingestion · UI · 114 tests |
| **1 · Production-ready** | 0–3 mo | Connect to bank's transaction-monitoring feed · **live sanctions/PEP lists (UN/OFAC/EU/BNM)** · SSO + role-based access · audit hardening · production OCR |
| **2 · Pilot** | 3–6 mo | 1–2 design-partner pilots · tune rules/typologies on real data · scale the analyst feedback loop · case-management integration |
| **3 · Enterprise** | 6–12 mo | On-prem/multi-tenant packaging · **SOC 2 / ISO 27001** · explainability & regulator reporting · more typologies |
| **4 · Scale** | 12 mo+ | SEA expansion · adjacent modules (sanctions screening, KYC onboarding, monitoring rules engine) |

**BUSINESS / GO-TO-MARKET**

| Phase | Timeline | Milestones |
|---|---|---|
| **Now** | — | Prototype + demo; regulatory & compliance advisory onboard |
| **Q1** | 0–3 mo | 1–2 **design partners / LOIs**; refine ICP & pricing |
| **Q2** | 3–6 mo | **Paid pilots**; case studies; seed raise |
| **Q3** | 6–9 mo | First **production customer**; partnerships (core-banking / RegTech ecosystem) |
| **Q4** | 9–12 mo | Repeatable sales motion; expand seats & volume; begin SEA outreach |

**Speaker note:** Two honest near-term must-dos to be "real": (1) plug into the bank's actual transaction feed, (2) swap demo watchlists for live official sanctions lists. Say so — it shows you understand production.

---

## SLIDE 16 — Honest Status & Risks (optional but credible)

- 🚧 **Not yet production-grade** — needs real data integration, live official watchlists, security certs (SOC 2/ISO 27001).
- 🧪 Rules/typologies are demo-calibrated — must be tuned per institution.
- 🔌 Requires integration with each bank's monitoring stack (effort per deployment).
- 🤝 Regulatory acceptance is a sales gate — mitigated by the **human-in-the-loop + full audit trail** design.

**Speaker note:** Including a credible risk slide builds trust with sophisticated investors/judges. The mitigations are baked into the architecture.

---

## SLIDE 17 — The Ask / Close

- **What we're building:** the private, auditable AI analyst for AML compliance.
- **Why we win:** local LLM (privacy) + hybrid rules-AI (auditability) + end-to-end automation.
- **The ask:** [design partners / pilot banks / RM ___ seed / mentorship / regulatory intros].
- **Vision:** every reporting institution in SEA investigates suspicious activity in minutes, privately, with a perfect audit trail.

**Speaker note:** Close on the vision + a specific, concrete ask.

---

## APPENDIX A — Live Demo Script (2–3 min)

1. **Dashboard** → metrics + self-learning banner.
2. **New Investigation** → type a customer name (show it **validate an existing customer** vs **auto-assign an ID for a new one**).
3. **Upload a bank statement** (`sample_statement_maybank.pdf`) → fields + 14 transactions auto-extracted. *(Optional: upload the scanned version to show OCR.)*
4. **Run** → watch the **14 agents stream live**.
5. **Open the case** → risk gauge, evidence, network graph, triggered rules, policy citations.
6. **SAR preview** → branded regulator-style PDF; download PDF/DOCX.
7. **Audit Logs / Settings** → governance versioning, rules, models.

---

## APPENDIX B — Talking-Point Soundbites

- *"Copilot, not autopilot — the human always signs off."*
- *"Rules make the decision; the AI explains it. No hallucinated verdicts."*
- *"The LLM runs on the bank's own servers — customer data never leaves the building."*
- *"95% of alerts are noise. We clear the noise and hand analysts the 5% that matters, pre-investigated."*
- *"It even reads a scanned statement and finds the structuring."*
- *"Every decision is evidence-backed and version-stamped — audit-ready by design."*

---

## APPENDIX C — Glossary (for non-AML audiences)

- **AML** — Anti-Money Laundering.
- **STR / SAR** — Suspicious Transaction / Activity Report filed to the regulator.
- **BNM / FIED** — Bank Negara Malaysia / its Financial Intelligence & Enforcement Dept.
- **AMLA 2001** — Malaysia's Anti-Money Laundering Act.
- **False positive** — a flagged transaction that turns out to be legitimate.
- **Structuring / smurfing** — splitting transfers to stay under reporting thresholds.
- **Layering / mule** — moving funds through intermediaries to obscure origin.
- **KYC** — Know Your Customer (identity/profile data).
- **PEP** — Politically Exposed Person (higher-risk).
- **RAG** — Retrieval-Augmented Generation (grounding AI answers in real documents).
```
