"use client";

import { useEffect, useState } from "react";
import { api, type CaseSummary } from "@/lib/api";
import { Card, CardLabel, Spinner } from "@/components/ui";
import { Folder, AlertTriangle, ShieldCheck, FileText, TrendingDown, Gauge } from "lucide-react";

const TYP_COLOR = "#f97316";
const RISK_COLORS: Record<string, string> = { CRITICAL: "#dc2626", HIGH: "#dc2626", MEDIUM: "#b45309", LOW: "#16a34a" };
const STATUS_COLOR = "#2563eb";

export default function Analytics() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.cases().then(setCases).catch(() => setCases([])).finally(() => setLoading(false)); }, []);

  if (loading) return <Wrap><Spinner label="loading analytics…" /></Wrap>;

  const total = cases.length;
  const high = cases.filter((c) => ["HIGH", "CRITICAL"].includes((c.risk_level || "").toUpperCase())).length;
  const auto = cases.filter((c) => /LOW_RISK|AUTO_CLOSED|CLEAR/.test((c.status || "").toUpperCase())).length;
  const sar = cases.filter((c) => /SAR|APPROVED|AWAITING/.test((c.status || "").toUpperCase())).length;
  const fpDenom = auto + sar;
  const avgRisk = total ? Math.round(cases.reduce((s, c) => s + (c.risk_score || 0), 0) / total) : 0;

  const byTyp = group(cases, (c) => c.typology || c.alert_type || "Unknown");
  const byStatus = group(cases, (c) => prettify(c.status));
  const byRisk = group(cases, (c) => (c.risk_level || "Unknown").toUpperCase());

  return (
    <Wrap>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <Metric icon={<Folder size={16} />} label="Total cases" value={String(total)} sub="processed" tone="blue" />
        <Metric icon={<AlertTriangle size={16} />} label="High-risk" value={String(high)} sub={total ? `${Math.round((high / total) * 100)}% of volume` : "—"} tone="red" />
        <Metric icon={<ShieldCheck size={16} />} label="Auto-cleared" value={String(auto)} sub="false positives" tone="green" />
        <Metric icon={<FileText size={16} />} label="SAR pipeline" value={String(sar)} sub="escalated" tone="orange" />
        <Metric icon={<TrendingDown size={16} />} label="FP reduction" value={fpDenom ? `${Math.round((auto / fpDenom) * 100)}%` : "—"} sub="cleared w/o human" tone="violet" />
        <Metric icon={<Gauge size={16} />} label="Avg risk score" value={`${avgRisk}`} sub="/ 100" tone="amber" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardLabel>Cases by typology</CardLabel>
          <Bars data={byTyp} color={() => TYP_COLOR} />
        </Card>
        <Card>
          <CardLabel>Cases by risk level</CardLabel>
          <Bars data={byRisk} color={(k) => RISK_COLORS[k] || "#9ca3af"} />
        </Card>
        <Card className="lg:col-span-2">
          <CardLabel>Cases by status</CardLabel>
          <Bars data={byStatus} color={() => STATUS_COLOR} />
        </Card>
      </div>
      {total === 0 && <p className="text-sm text-ink3">No cases yet — run investigations to populate analytics.</p>}
    </Wrap>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Analytics</h1>
        <p className="text-sm text-ink2">Aggregate triage & false-positive metrics</p>
      </div>
      {children}
    </div>
  );
}

function Metric({ icon, label, value, sub, tone }: { icon: React.ReactNode; label: string; value: string; sub: string; tone: string }) {
  const ring: Record<string, string> = {
    blue: "bg-blue-bg text-blue", red: "bg-red-bg text-red", green: "bg-green-bg text-green",
    orange: "bg-primary-soft text-primary-press", violet: "bg-violet-bg text-violet", amber: "bg-amber-bg text-amber",
  };
  return (
    <Card>
      <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${ring[tone]}`}>{icon}</span>
      <div className="mt-2 text-2xl font-extrabold tracking-tight">{value}</div>
      <div className="text-[11px] font-semibold text-ink2">{label}</div>
      <div className="text-[11px] text-ink3">{sub}</div>
    </Card>
  );
}

function Bars({ data, color }: { data: [string, number][]; color: (k: string) => string }) {
  const max = Math.max(1, ...data.map(([, v]) => v));
  return (
    <div className="mt-3 space-y-2.5">
      {data.length === 0 && <p className="text-sm text-ink3">No data.</p>}
      {data.map(([k, v]) => (
        <div key={k}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-ink2 capitalize">{k.toLowerCase()}</span>
            <span className="mono font-semibold text-ink">{v}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-soft2">
            <div className="h-full rounded-full" style={{ width: `${(v / max) * 100}%`, background: color(k) }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function group(cases: CaseSummary[], key: (c: CaseSummary) => string): [string, number][] {
  const m = new Map<string, number>();
  for (const c of cases) { const k = key(c); m.set(k, (m.get(k) || 0) + 1); }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}
function prettify(s?: string) { return (s || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (x) => x.toUpperCase()); }
