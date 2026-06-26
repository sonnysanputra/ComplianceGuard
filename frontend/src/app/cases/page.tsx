"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type CaseSummary } from "@/lib/api";
import { Card, Pill, Spinner, riskTone, priorityTone, statusTone, prettyStatus } from "@/components/ui";

export default function CasesPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.cases().then(setCases).catch(() => setCases([])).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Cases</h1>
        <p className="text-sm text-ink2">All investigated cases in the audit store</p>
      </div>

      <Card pad={false}>
        {loading ? (
          <div className="p-6"><Spinner label="loading cases…" /></div>
        ) : cases.length === 0 ? (
          <p className="p-6 text-sm text-ink3">No cases yet — run a scenario from the Dashboard.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-ink3">
                <th className="px-5 py-3 font-semibold">Case</th>
                <th className="px-5 py-3 font-semibold">Customer</th>
                <th className="px-5 py-3 font-semibold">Typology</th>
                <th className="px-5 py-3 font-semibold">Risk</th>
                <th className="px-5 py-3 font-semibold">Priority</th>
                <th className="px-5 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {cases.map((c) => (
                <tr key={c.case_id} className="hover:bg-soft">
                  <td className="px-5 py-3">
                    <Link href={`/case/${encodeURIComponent(c.case_id)}`} className="mono font-semibold text-primary-press hover:underline">{c.case_id}</Link>
                  </td>
                  <td className="px-5 py-3 mono text-xs text-ink2">{c.customer_id}</td>
                  <td className="px-5 py-3 capitalize">{c.typology || c.alert_type || "—"}</td>
                  <td className="px-5 py-3">
                    <span className="mono mr-2 font-semibold">{c.risk_score ?? "—"}</span>
                    <Pill tone={riskTone(c.risk_level)}>{prettyStatus(c.risk_level)}</Pill>
                  </td>
                  <td className="px-5 py-3"><Pill tone={priorityTone(c.priority)}>{c.priority || "—"}</Pill></td>
                  <td className="px-5 py-3"><Pill tone={statusTone(c.status)} dot>{prettyStatus(c.status)}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
