"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type AuditEvent } from "@/lib/api";
import { Card, CardLabel, Pill, Spinner, pct } from "@/components/ui";
import { Bot, User, Cpu } from "lucide-react";

export default function AuditLogs() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [gov, setGov] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.auditEvents(150)
      .then((r) => { setEvents(r.events || []); setGov(r.governance || {}); })
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = events.filter((e) =>
    !q || `${e.case_id} ${e.agent_name} ${e.message}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Audit Logs</h1>
          <p className="text-sm text-ink2">Full agent + decision audit trail across all cases</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs text-ink2">
          <Cpu size={14} className="text-primary" />
          model <b className="mono text-ink">{gov.model || "—"}</b> · ruleset <b className="mono text-ink">{gov.ruleset || "—"}</b> · policy <b className="mono text-ink">{(gov.policy || "—").slice(0, 14)}</b>
        </div>
      </div>

      <Card pad={false}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <CardLabel>{filtered.length} events</CardLabel>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by case, agent, action…"
                 className="w-64 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm outline-none focus:border-primary" />
        </div>
        {loading ? (
          <div className="p-6"><Spinner label="loading events…" /></div>
        ) : filtered.length === 0 ? (
          <p className="p-6 text-sm text-ink3">No audit events yet — run an investigation (and ensure Supabase is configured).</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-ink3">
                  <th className="px-5 py-2 font-semibold">Time</th>
                  <th className="px-5 py-2 font-semibold">Case</th>
                  <th className="px-5 py-2 font-semibold">Actor</th>
                  <th className="px-5 py-2 font-semibold">Action</th>
                  <th className="px-5 py-2 font-semibold">Conf.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((e, i) => {
                  const human = (e.agent_name || "").toLowerCase().includes("human");
                  return (
                    <tr key={e.id ?? i} className="hover:bg-soft">
                      <td className="whitespace-nowrap px-5 py-2.5 text-xs text-ink3">{fmt(e.created_at)}</td>
                      <td className="px-5 py-2.5">
                        <Link href={`/case/${encodeURIComponent(e.case_id || "")}`} className="mono text-xs font-semibold text-primary-press hover:underline">{e.case_id}</Link>
                      </td>
                      <td className="px-5 py-2.5">
                        <span className="inline-flex items-center gap-1.5">
                          <span className={`flex h-5 w-5 items-center justify-center rounded-full ${human ? "bg-violet-bg text-violet" : "bg-primary-soft text-primary-press"}`}>
                            {human ? <User size={11} /> : <Bot size={11} />}
                          </span>
                          <span className="text-xs font-medium">{label(e.agent_name)}</span>
                        </span>
                      </td>
                      <td className="px-5 py-2.5 text-xs text-ink2">{e.message}</td>
                      <td className="px-5 py-2.5">
                        {e.confidence != null ? <Pill tone={e.confidence >= 0.8 ? "green" : e.confidence >= 0.5 ? "amber" : "slate"}>{pct(e.confidence)}</Pill> : <span className="text-ink3">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function fmt(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}
function label(a?: string) {
  return (a || "—").split("_").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}
