"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type CaseSummary, type Scenario } from "@/lib/api";
import { Card, CardLabel, Pill, Spinner, statusTone, prettyStatus } from "@/components/ui";
import RunDialog from "@/components/RunDialog";
import { Play, RefreshCw, TrendingDown, FolderCheck, FileText, Layers, Plus } from "lucide-react";

export default function Dashboard() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [run, setRun] = useState<Scenario | null>(null);

  async function load() {
    try {
      const [s, c] = await Promise.all([api.scenarios(), api.cases().catch(() => [])]);
      setScenarios(s); setCases(c); setErr(null);
    } catch {
      setErr("Cannot reach the backend at :8000. Start it from backend/ with `python server.py`.");
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const s = stats(cases);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Dashboard</h1>
          <p className="text-sm text-ink2">AML alert triage & investigation overview</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink2 hover:bg-soft2">
            <RefreshCw size={14} /> Refresh
          </button>
          <Link href="/new" className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-primary-deep">
            <Plus size={15} /> New Investigation
          </Link>
        </div>
      </div>

      {err && <div className="rounded-xl border border-red-border bg-red-bg px-4 py-3 text-sm text-red">{err}</div>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Metric icon={<Layers size={18} />} label="Cases processed" value={String(s.total)} hint="in the audit store" tone="blue" />
        <Metric icon={<FolderCheck size={18} />} label="Auto-cleared" value={String(s.auto)} hint="low-risk / false positives" tone="green" />
        <Metric icon={<FileText size={18} />} label="Escalated to SAR" value={String(s.sar)} hint="high-risk → analyst" tone="orange" />
        <Metric icon={<TrendingDown size={18} />} label="FP reduction" value={s.fp} hint="cleared without a human" tone="violet" />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Card>
            <CardLabel>Run a new investigation</CardLabel>
            <p className="mt-0.5 text-sm text-ink2">Pick a demo alert — agents stream live as they work.</p>
            {loading ? (
              <div className="mt-4"><Spinner label="loading scenarios…" /></div>
            ) : (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {scenarios.map((sc) => (
                  <div key={sc.id} className="flex flex-col rounded-xl border border-line bg-soft p-3.5">
                    <div className="flex items-center justify-between">
                      <span className="mono text-xs font-semibold text-primary-press">{sc.id}</span>
                      <span className="mono text-[11px] text-ink3">{sc.customer_id}</span>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-sm text-ink">{sc.reason}</p>
                    {sc._expected && <div className="mt-2 rounded-lg bg-surface px-2 py-1 text-[11px] text-ink2">{sc._expected}</div>}
                    <button
                      onClick={() => setRun(sc)}
                      className="mt-3 inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-deep"
                    >
                      <Play size={14} /> Run investigation
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card pad={false}>
            <div className="flex items-center justify-between px-5 py-3.5">
              <CardLabel>Recent cases</CardLabel>
              <Link href="/cases" className="text-xs font-semibold text-primary-press hover:underline">View all →</Link>
            </div>
            <div className="divide-y divide-line">
              {cases.length === 0 && <p className="px-5 py-6 text-sm text-ink3">No cases yet.</p>}
              {cases.slice(0, 6).map((c) => (
                <Link key={c.case_id} href={`/case/${encodeURIComponent(c.case_id)}`} className="flex items-center gap-3 px-5 py-3 hover:bg-soft">
                  <div className="min-w-0 flex-1">
                    <div className="mono text-sm font-semibold text-ink">{c.case_id}</div>
                    <div className="truncate text-xs text-ink3">{c.typology || c.alert_type || "—"} · {c.customer_id}</div>
                  </div>
                  <span className="mono text-sm font-semibold text-ink">{c.risk_score ?? "—"}</span>
                  <Pill tone={statusTone(c.status)}>{prettyStatus(c.status)}</Pill>
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {run && <RunDialog scenario={run} onClose={() => { setRun(null); load(); }} />}
    </div>
  );
}

function Metric({ icon, label, value, hint, tone }: { icon: React.ReactNode; label: string; value: string; hint: string; tone: "blue" | "green" | "orange" | "violet" }) {
  const ring: Record<string, string> = {
    blue: "bg-blue-bg text-blue", green: "bg-green-bg text-green",
    orange: "bg-primary-soft text-primary-press", violet: "bg-violet-bg text-violet",
  };
  return (
    <Card>
      <div className="flex items-start justify-between">
        <CardLabel>{label}</CardLabel>
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${ring[tone]}`}>{icon}</span>
      </div>
      <div className="mt-2 text-3xl font-extrabold tracking-tight">{value}</div>
      <div className="mt-0.5 text-[11px] text-ink3">{hint}</div>
    </Card>
  );
}

function stats(cases: CaseSummary[]) {
  const has = (c: CaseSummary, ...k: string[]) => k.some((x) => (c.status || "").toUpperCase().includes(x));
  const total = cases.length;
  const auto = cases.filter((c) => has(c, "LOW_RISK", "AUTO_CLOSED", "CLEAR")).length;
  const sar = cases.filter((c) => has(c, "SAR", "APPROVED", "AWAITING")).length;
  const denom = auto + sar;
  return { total, auto, sar, fp: denom ? `${Math.round((auto / denom) * 100)}%` : "—" };
}
