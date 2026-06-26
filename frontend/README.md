# ComplianceGuard AI — Frontend

Next.js + TypeScript + Tailwind dashboard for the CompliGuard AML backend, styled
to the ComplianceGuard design (light theme, orange accent, Manrope + IBM Plex Mono).

- **Dashboard** — triage metrics, run a live streaming investigation, recent cases
- **Investigation Workspace** (`/case/[id]`) — CASE card, multi-agent flow, risk
  gauge, data quality, triggered rules (with evidence IDs), transaction timeline,
  money-flow network graph, evidence register, policy citations, clearance note,
  SAR draft (PDF/DOCX/MD export), and the analyst approve/reject decision bar
- **Cases**, **Policies / RAG Library**, and Analytics / Audit / Settings sections

## Run (two terminals)

```bash
# 1) backend  (from backend/, Ollama + Supabase configured)
python server.py            # FastAPI on http://localhost:8000

# 2) frontend (from frontend/)
npm install                 # first time only
npm run dev                 # http://localhost:3000
```

CORS is already open on the backend (`allow_origins=["*"]`). Point the UI elsewhere
via `.env.local` → `NEXT_PUBLIC_API_BASE`.

> A live investigation runs the local Qwen model (~1–2 min on CPU); the stream UI
> shows each agent completing so the wait is visible. Cases/metrics load instantly.
