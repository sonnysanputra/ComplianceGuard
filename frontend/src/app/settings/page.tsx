"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardLabel, Pill, Spinner } from "@/components/ui";
import { Cpu, BookOpen, SlidersHorizontal, Globe, RefreshCw, Database, CheckCircle2 } from "lucide-react";

interface Config {
  chat_model?: string; embed_model?: string; reranker?: string;
  ruleset_version?: string; policy_version?: string;
  escalation_threshold?: number; policy_count?: number; country_risk_count?: number;
}
interface Rule { rule_id?: string; name?: string; risk_points?: number; severity?: string }

export default function Settings() {
  const [cfg, setCfg] = useState<Config>({});
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  async function load() {
    try {
      const [c, r] = await Promise.all([api.config(), api.rules().catch(() => ({}))]);
      setCfg(c as Config);
      setRules(((r as Record<string, unknown>).typology_rules as Rule[]) || []);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    try { await fn(); setToast(`${label} done.`); await load(); }
    catch { setToast(`${label} failed — is the backend running?`); }
    finally { setBusy(null); setTimeout(() => setToast(null), 3000); }
  }

  if (loading) return <Wrap><Spinner label="loading settings…" /></Wrap>;

  return (
    <Wrap>
      {toast && <div className="rounded-lg border border-green-border bg-green-bg px-4 py-2 text-sm text-green">{toast}</div>}

      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <Head icon={<SlidersHorizontal size={16} />} title="Risk threshold" />
          <div className="mt-2 flex items-end gap-2">
            <span className="text-4xl font-extrabold">{cfg.escalation_threshold ?? "—"}</span>
            <span className="pb-1.5 text-sm text-ink3">/ 100</span>
          </div>
          <p className="mt-1 text-xs text-ink3">Score at or above this escalates to a SAR. Configured in <span className="mono">aml_rules.yaml</span>.</p>
        </Card>

        <Card>
          <Head icon={<Cpu size={16} />} title="Models" />
          <dl className="mt-2 space-y-1.5 text-sm">
            <KV k="Reasoning (LLM)" v={cfg.chat_model} />
            <KV k="Embeddings" v={cfg.embed_model} />
            <KV k="Reranker" v={cfg.reranker} />
          </dl>
        </Card>

        <Card>
          <Head icon={<Database size={16} />} title="Governance versions" />
          <dl className="mt-2 space-y-1.5 text-sm">
            <KV k="Ruleset" v={cfg.ruleset_version} />
            <KV k="Policy index" v={cfg.policy_version} />
          </dl>
        </Card>

        <Card>
          <Head icon={<BookOpen size={16} />} title="Policy / RAG library" />
          <div className="mt-2 text-3xl font-extrabold">{cfg.policy_count ?? "—"}</div>
          <p className="text-xs text-ink3">policy documents indexed</p>
          <button disabled={busy !== null} onClick={() => act("Re-index policies", api.reindexPolicies)}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm font-semibold text-ink2 hover:bg-soft2 disabled:opacity-50">
            <RefreshCw size={14} className={busy === "Re-index policies" ? "animate-spin" : ""} /> Re-index
          </button>
        </Card>

        <Card>
          <Head icon={<Globe size={16} />} title="Country-risk register" />
          <div className="mt-2 text-3xl font-extrabold">{cfg.country_risk_count ?? "—"}</div>
          <p className="text-xs text-ink3">jurisdictions on file</p>
        </Card>

        <Card>
          <Head icon={<SlidersHorizontal size={16} />} title="Rule engine" />
          <p className="mt-2 text-xs text-ink3">Reload the AML ruleset + country-risk register from disk without a restart.</p>
          <button disabled={busy !== null} onClick={() => act("Reload rules", api.reloadRules)}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-deep disabled:opacity-50">
            <RefreshCw size={14} className={busy === "Reload rules" ? "animate-spin" : ""} /> Reload rules
          </button>
        </Card>
      </div>

      <Card pad={false}>
        <div className="border-b border-line px-5 py-3"><CardLabel>Detection rules ({rules.length})</CardLabel></div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-ink3">
              <th className="px-5 py-2 font-semibold">Rule</th>
              <th className="px-5 py-2 font-semibold">Name</th>
              <th className="px-5 py-2 font-semibold">Points</th>
              <th className="px-5 py-2 font-semibold">Severity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rules.map((r, i) => (
              <tr key={r.rule_id ?? i}>
                <td className="px-5 py-2 mono text-xs text-primary-press">{r.rule_id}</td>
                <td className="px-5 py-2">{r.name}</td>
                <td className="px-5 py-2 mono font-semibold">+{r.risk_points}</td>
                <td className="px-5 py-2"><Pill tone={sevTone(r.severity)}>{r.severity}</Pill></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center gap-2 text-xs text-ink3">
        <CheckCircle2 size={14} className="text-green" /> Connected to backend at the configured API base.
      </div>
    </Wrap>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Settings</h1>
        <p className="text-sm text-ink2">Rule thresholds, models & integrations</p>
      </div>
      {children}
    </div>
  );
}
function Head({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <div className="flex items-center gap-2"><span className="text-primary">{icon}</span><CardLabel>{title}</CardLabel></div>;
}
function KV({ k, v }: { k: string; v?: string }) {
  return <div className="flex justify-between gap-3"><dt className="text-ink3">{k}</dt><dd className="mono text-right text-ink">{v || "—"}</dd></div>;
}
function sevTone(s?: string): "red" | "amber" | "blue" | "slate" {
  const k = (s || "").toUpperCase();
  if (k.includes("HIGH") || k === "CRITICAL") return "red";
  if (k.includes("MEDIUM")) return "amber";
  if (k === "LOW") return "blue";
  return "slate";
}
