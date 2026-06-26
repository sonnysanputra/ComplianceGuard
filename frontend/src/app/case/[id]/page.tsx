"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  api, type CaseSnapshot, type EvidenceItem, type RiskFactor, type TimelineEvent, type PolicyCitation,
} from "@/lib/api";
import {
  Card, CardLabel, Pill, Spinner, RiskGauge, rm, pct,
  riskTone, priorityTone, statusTone, prettyStatus,
} from "@/components/ui";
import {
  Check, Clock, FileText, ChevronRight, Zap, ArrowRight, ArrowLeft,
} from "lucide-react";

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [snap, setSnap] = useState<CaseSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setSnap(await api.case(id)); setErr(null); }
    catch { setErr("Could not load this case."); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <Spinner label="loading case…" />;
  if (err || !snap) return <div className="text-red">{err || "Not found"}</div>;

  const tri = (snap.triage || {}) as Record<string, unknown>;
  const kyc = (snap.kyc_findings || {}) as Record<string, unknown>;
  const dq = (snap.data_quality || {}) as Record<string, unknown>;
  const typology = String(snap.transaction_findings?.["typology"] || tri.alert_type || "Alert");
  const awaiting = (snap.status || "").toUpperCase().includes("AWAITING");
  const rats = snap.audit_rationales || [];
  const done = rats.length;

  return (
    <div className="space-y-5 pb-24">
      {/* Breadcrumb + title */}
      <div className="flex items-center gap-1.5 text-sm text-ink3">
        <Link href="/cases" className="hover:text-ink2">Investigation Workspace</Link>
        <ChevronRight size={14} />
        <span className="mono text-ink2">{snap.case_id}</span>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-3xl font-extrabold capitalize tracking-tight">{typology}</h1>
            <Pill tone={statusTone(snap.status)} dot>{prettyStatus(snap.status)}</Pill>
          </div>
          <p className="mt-1 text-sm text-ink2">{String(tri.alert_reason || tri.reason || snap.transaction_findings?.["summary"] || "")}</p>
        </div>
        {snap.sar_draft && (
          <a href={api.sarExportUrl(snap.case_id, "pdf")} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-semibold text-ink hover:bg-soft2">
            <FileText size={16} /> SAR Draft
          </a>
        )}
      </div>

      {/* Top 3 cards */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* CASE */}
        <Card pad={false} className="overflow-hidden">
          <div className="bg-primary-soft px-5 py-4">
            <CardLabel>Case</CardLabel>
            <div className="mt-1 flex items-center justify-between">
              <span className="mono text-xl font-bold tracking-tight">{snap.case_id}</span>
              <Pill tone={riskTone(snap.risk_level)} dot>{prettyStatus(snap.risk_level)} Risk</Pill>
            </div>
            <div className="mt-1 flex items-center gap-2 text-sm text-ink2">
              Customer <span className="mono rounded bg-surface px-1.5 py-0.5 text-xs">{String((tri.entities as Record<string, unknown>)?.customer_id || tri.customer_id || "—")}</span>
            </div>
          </div>
          <dl className="divide-y divide-line">
            <Row k="KYC status" v={String(kyc.kyc_status || "—")} />
            <Row k="Consistency" v={String(kyc.consistency || "—")} />
            <Row k="Occupation" v={String(kyc.occupation || "—")} />
            <Row k="Declared income" v={kyc.declared_income ? `${rm(kyc.declared_income as number)} / mo` : "—"} />
            <Row k="Account age" v={kyc.account_age_months ? `${kyc.account_age_months} months` : "—"} />
            <Row k="Previous alerts" v={String(kyc.previous_alerts ?? "—")} />
            <Row k="EDD required" v={kyc.edd_required ? "Yes" : "No"} />
          </dl>
        </Card>

        {/* Multi-agent flow */}
        <Card>
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-primary" />
            <h3 className="text-base font-bold leading-tight">Multi-Agent<br />Investigation Flow</h3>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <Pill tone="green" dot>{done} done</Pill>
            {awaiting && <Pill tone="amber" dot>1 attention</Pill>}
            <span className="text-ink3">· {done + (awaiting ? 1 : 0)} agents · evidence-backed</span>
          </div>
          <div className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1">
            {rats.map((r, i) => (
              <div key={i} className="flex items-start gap-2.5 rounded-lg border border-line bg-soft px-2.5 py-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-bg text-green"><Check size={12} /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{label(r.agent)}</span>
                    <span className="mono text-[11px] text-ink3">{pct(r.confidence)}</span>
                  </div>
                  <p className="line-clamp-2 text-xs text-ink3">{r.rationale}</p>
                </div>
              </div>
            ))}
            {awaiting && (
              <div className="flex items-start gap-2.5 rounded-lg border border-amber-border bg-amber-bg px-2.5 py-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface text-amber"><Clock size={12} /></span>
                <div className="text-sm font-semibold text-amber">Human Approval — awaiting decision</div>
              </div>
            )}
          </div>
        </Card>

        {/* Risk gauge */}
        <Card>
          <CardLabel>Risk Assessment</CardLabel>
          <div className="mt-2 flex flex-col items-center">
            <RiskGauge value={snap.risk_score} level={snap.risk_level} size={188} />
            <div className="mt-2"><Pill tone={riskTone(snap.risk_level)} dot>{prettyStatus(snap.risk_level)} Risk</Pill></div>
          </div>
          <div className="mt-4">
            <div className="h-2 w-full rounded-full bg-gradient-to-r from-green via-amber to-red" />
            <div className="mt-1 flex justify-between text-[11px] text-ink3"><span>Low</span><span>Medium</span><span>High</span></div>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-ink2">Model confidence</span>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-24 overflow-hidden rounded-full bg-soft2">
                <div className="h-full rounded-full bg-primary" style={{ width: pct(snap.confidence) }} />
              </div>
              <span className="mono font-semibold">{pct(snap.confidence)}</span>
            </div>
          </div>
          <div className="mt-2 flex items-center gap-3 text-xs text-ink3">
            <span>rule <b className="mono text-ink2">{snap.rule_score ?? "—"}</b></span>
            <span>AI <b className="mono text-ink2">{snap.ai_score ?? "—"}</b></span>
            {snap.priority && <span className="ml-auto"><Pill tone={priorityTone(snap.priority)}>{snap.priority}</Pill></span>}
          </div>
        </Card>
      </div>

      {/* Detail cards */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Data quality */}
        <Card>
          <div className="flex items-center justify-between">
            <CardLabel>Data Quality</CardLabel>
            <Pill tone={String(dq.severity).includes("GOOD") ? "green" : String(dq.severity).includes("PARTIAL") ? "amber" : "red"}>
              {String(dq.severity || "—")}
            </Pill>
          </div>
          <div className="mt-2 flex items-end gap-2">
            <span className="text-3xl font-extrabold">{String(dq.quality_score ?? "—")}</span>
            <span className="pb-1 text-sm text-ink3">/ 100</span>
          </div>
          <p className="mt-1 text-sm text-ink2">{String(dq.recommended_action || "")}</p>
        </Card>

        {/* Triggered rules */}
        <Card>
          <CardLabel>Triggered Rules ({(snap.risk_factors || []).length})</CardLabel>
          <div className="mt-2 space-y-2">
            {(snap.risk_factors || []).length === 0 && <p className="text-sm text-ink3">No rules triggered.</p>}
            {(snap.risk_factors || []).map((f: RiskFactor, i) => (
              <div key={i} className="flex items-start gap-3 rounded-lg border border-line bg-soft p-2.5">
                <span className={`mono text-sm font-bold ${(f.points ?? 0) < 0 ? "text-green" : "text-primary-press"}`}>
                  {(f.points ?? 0) >= 0 ? "+" : ""}{f.points}
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{f.factor || f.name} <span className="mono text-[11px] text-ink3">{f.rule_id}</span></div>
                  <div className="text-xs text-ink3">{f.evidence}</div>
                  {f.evidence_ids && f.evidence_ids.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {f.evidence_ids.map((e) => <span key={e} className="mono rounded bg-blue-bg px-1 text-[10px] text-blue">{e}</span>)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Timeline */}
        <Card>
          <CardLabel>Transaction Timeline</CardLabel>
          <Timeline tl={(snap.timeline_findings?.timeline || []) as TimelineEvent[]} />
        </Card>

        {/* Network */}
        <Card>
          <CardLabel>Money-Flow Network</CardLabel>
          <Network snap={snap} />
        </Card>

        {/* Clearance note */}
        {snap.clearance_note && (
          <Card>
            <div className="flex items-center justify-between">
              <CardLabel>Clearance Note</CardLabel>
              <Pill tone="green">Auto-cleared</Pill>
            </div>
            <p className="mt-2 text-sm text-ink">{snap.clearance_note.clearance_reason}</p>
            <ul className="mt-2 space-y-1 text-xs text-ink2">
              {(snap.clearance_note.evidence || []).map((e, i) => <li key={i} className="flex gap-1.5"><Check size={13} className="mt-0.5 text-green" /> {e}</li>)}
            </ul>
            <p className="mt-2 text-xs font-semibold text-green">→ {snap.clearance_note.recommended_action}</p>
          </Card>
        )}

        {/* Policies */}
        <Card>
          <CardLabel>Policy Citations ({(snap.retrieved_policies || []).length})</CardLabel>
          <div className="mt-2 space-y-2">
            {(snap.retrieved_policies || []).length === 0 && <p className="text-sm text-ink3">No policies retrieved.</p>}
            {(snap.retrieved_policies as PolicyCitation[] || []).map((p, i) => (
              <div key={i} className="rounded-lg border border-line bg-soft p-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm"><span className="mono font-semibold text-primary-press">{p.policy_id}</span> · {p.title}</span>
                  <span className="mono text-[11px] text-ink3">rerank {p.rerank_score?.toFixed(2) ?? "—"}</span>
                </div>
                <div className="text-xs text-ink3">section {p.section} · {p.category}</div>
              </div>
            ))}
          </div>
        </Card>

        {/* Evidence */}
        <Card className="lg:col-span-2">
          <CardLabel>Evidence Register ({(snap.evidence || []).length})</CardLabel>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-ink3">
                  <th className="pb-2 pr-3">ID</th><th className="pb-2 pr-3">Source</th><th className="pb-2 pr-3">Field</th><th className="pb-2 pr-3">Value</th><th className="pb-2">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {(snap.evidence as EvidenceItem[] || []).map((e) => (
                  <tr key={e.evidence_id}>
                    <td className="py-1.5 pr-3 mono text-xs font-semibold text-primary-press">{e.evidence_id}</td>
                    <td className="py-1.5 pr-3 text-xs text-ink2">{e.source_type} <span className="mono text-ink3">/ {e.source_id}</span></td>
                    <td className="py-1.5 pr-3 text-xs">{e.field}</td>
                    <td className="py-1.5 pr-3 mono text-xs">{String(e.value)}</td>
                    <td className="py-1.5 text-xs text-ink2">{e.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* SAR */}
        {snap.sar_draft && (
          <Card className="lg:col-span-2">
            <div className="flex items-center justify-between">
              <CardLabel>SAR Draft (regulator-style)</CardLabel>
              <div className="flex gap-2">
                {(["pdf", "docx", "markdown"] as const).map((f) => (
                  <a key={f} href={api.sarExportUrl(snap.case_id, f)} className="rounded-md border border-line px-2 py-0.5 text-[11px] text-ink2 hover:bg-soft2">{f}</a>
                ))}
              </div>
            </div>
            <pre className="mono mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl bg-soft p-3 text-xs text-ink2">{snap.sar_draft}</pre>
          </Card>
        )}
      </div>

      {awaiting && <DecisionBar caseId={snap.case_id} onDone={load} />}
    </div>
  );
}

function Timeline({ tl }: { tl: TimelineEvent[] }) {
  if (tl.length === 0) return <p className="mt-2 text-sm text-ink3">No transactions.</p>;
  return (
    <ol className="mt-2 space-y-2">
      {tl.map((t, i) => {
        const inbound = String(t.direction).toUpperCase() === "IN";
        return (
          <li key={i} className="flex items-start gap-2.5 rounded-lg border border-line bg-soft p-2.5">
            <span className={`mt-0.5 flex h-6 w-6 items-center justify-center rounded-full ${inbound ? "bg-green-bg text-green" : "bg-blue-bg text-blue"}`}>
              {inbound ? <ArrowLeft size={13} /> : <ArrowRight size={13} />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="mono text-sm font-semibold">{rm(t.amount)} · {t.recipient}</span>
                <span className="mono text-[11px] text-ink3">{t.time}</span>
              </div>
              <div className="text-xs text-ink3">{t.country}{t.new_recipient ? " · NEW recipient" : ""}{t.purpose ? ` · ${t.purpose}` : ""}</div>
              {t.risk_note && <div className="mt-0.5 text-xs text-amber">⚑ {t.risk_note}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Network({ snap }: { snap: CaseSnapshot }) {
  const g = snap.graph_findings;
  if (!g || (g.graph_risk_score ?? 0) === 0)
    return <p className="mt-2 text-sm text-ink3">No network laundering signatures detected.</p>;
  const path = g.possible_layering_path || [];
  return (
    <div className="mt-2">
      <div className="grid grid-cols-4 gap-2">
        {[["Graph risk", `${g.graph_risk_score}/30`], ["Fan-out", g.fan_out_count], ["Fan-in", g.fan_in_count], ["Hops", g.hop_count]].map(([k, v]) => (
          <div key={String(k)} className="rounded-lg border border-line bg-soft p-2 text-center">
            <div className="text-lg font-bold">{String(v ?? 0)}</div>
            <div className="text-[10px] text-ink3">{k}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {g.rapid_forwarding_detected && <Pill tone="amber">rapid forwarding</Pill>}
        {g.circular_flow && <Pill tone="red">circular flow</Pill>}
        {g.common_recipient && g.common_recipient.length > 0 && <Pill tone="amber">collector: {g.common_recipient.join(", ")}</Pill>}
      </div>
      {path.length >= 2 && (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wider text-ink3">Possible layering path</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {path.map((n, i) => (
              <span key={i} className="flex items-center gap-1.5">
                <span className="mono rounded-lg border border-primary-border bg-primary-soft px-2 py-1 text-xs text-primary-press">{n}</span>
                {i < path.length - 1 && <ArrowRight size={13} className="text-ink3" />}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DecisionBar({ caseId, onDone }: { caseId: string; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function decide(decision: string) {
    setBusy(true);
    try {
      await api.decide(caseId, { decision, analyst_id: "analyst-ui", analyst_note: note || null, analyst_agrees_with_ai: decision === "approve" });
      onDone();
    } finally { setBusy(false); }
  }
  return (
    <div className="fixed bottom-5 left-1/2 z-30 w-[min(92vw,52rem)] -translate-x-1/2 rounded-2xl border border-primary-border bg-surface/95 p-3 shadow-cardlg backdrop-blur">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-primary-press">⏸ Analyst decision required</span>
        <input
          value={note} onChange={(e) => setNote(e.target.value)} placeholder="note / reason (optional)"
          className="min-w-40 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm outline-none focus:border-primary"
        />
        <button disabled={busy} onClick={() => decide("approve")} className="rounded-lg bg-green px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">Approve</button>
        <button disabled={busy} onClick={() => decide("reject")} className="rounded-lg bg-red px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">Reject</button>
        <button disabled={busy} onClick={() => decide("request_more_info")} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-soft2 disabled:opacity-50">More info</button>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between px-5 py-2.5 text-sm">
      <dt className="text-ink3">{k}</dt>
      <dd className="font-semibold capitalize">{v}</dd>
    </div>
  );
}
function label(agent: string) {
  return agent.split("_").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}
