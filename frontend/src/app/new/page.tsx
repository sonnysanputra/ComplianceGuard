"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, streamInvestigation, type Scenario, type StreamProgress } from "@/lib/api";
import { Card, CardLabel, Spinner, pct } from "@/components/ui";
import { Play, Check, X } from "lucide-react";

interface Customer { customer_id: string; name?: string; occupation?: string; risk_category?: string }

function genId() {
  const d = new Date();
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  return `AML-${ymd}-${Math.floor(100 + Math.random() * 899)}`;
}

export default function NewInvestigation() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [form, setForm] = useState<Scenario>({
    id: genId(), customer_id: "", reason: "", recipient: "",
    country: "Malaysia", total_amount: 0, num_transactions: 1, supporting_document: "",
  });
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<StreamProgress[]>([]);
  const [done, setDone] = useState<{ case_id: string; status?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    fetch(`${API_BASE}/customers`, { cache: "no-store" })
      .then((r) => r.json())
      .then((cs: Customer[]) => {
        setCustomers(cs);
        if (cs[0]) setForm((f) => ({ ...f, customer_id: cs[0].customer_id }));
      })
      .catch(() => {});
  }, []);

  function set<K extends keyof Scenario>(k: K, v: Scenario[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function run() {
    if (!form.customer_id || !form.reason) return;
    if (startedRef.current) return;
    startedRef.current = true;
    setRunning(true);
    streamInvestigation(form, {
      onProgress: (p) => setEvents((e) => [...e, p]),
      onDone: (d) => setDone(d),
      onError: (e) => setError(e),
    });
  }

  const canRun = form.customer_id && form.reason.trim().length > 3;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">New Investigation</h1>
        <p className="text-sm text-ink2">Raise an alert against a customer and run the 16-agent investigation live.</p>
      </div>

      {!running ? (
        <Card>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Alert ID">
              <input value={form.id} onChange={(e) => set("id", e.target.value)} className={inp} />
            </Field>
            <Field label="Customer">
              <select value={form.customer_id} onChange={(e) => set("customer_id", e.target.value)} className={inp}>
                <option value="" disabled>Select a customer…</option>
                {customers.map((c) => (
                  <option key={c.customer_id} value={c.customer_id}>
                    {c.customer_id}{c.name && c.name !== c.customer_id ? ` — ${c.name}` : ""}{c.risk_category ? ` (${c.risk_category})` : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Alert reason" full>
              <input value={form.reason} onChange={(e) => set("reason", e.target.value)} placeholder="e.g. Multiple sub-threshold transfers to a new overseas recipient" className={inp} />
            </Field>
            <Field label="Recipient">
              <input value={form.recipient} onChange={(e) => set("recipient", e.target.value)} placeholder="e.g. Global Trade Ltd" className={inp} />
            </Field>
            <Field label="Destination country">
              <input value={form.country} onChange={(e) => set("country", e.target.value)} className={inp} />
            </Field>
            <Field label="Total amount (RM)">
              <input type="number" value={form.total_amount} onChange={(e) => set("total_amount", Number(e.target.value))} className={inp} />
            </Field>
            <Field label="Number of transactions">
              <input type="number" value={form.num_transactions} onChange={(e) => set("num_transactions", Number(e.target.value))} className={inp} />
            </Field>
            <Field label="Supporting document (optional)" full>
              <input value={form.supporting_document ?? ""} onChange={(e) => set("supporting_document", e.target.value)} placeholder="e.g. INV-2026-552" className={inp} />
            </Field>
          </div>

          <div className="mt-2 rounded-lg bg-soft px-3 py-2 text-xs text-ink3">
            Tip: pick an existing customer so the investigation has transaction history to analyse. A
            customer with no data on file will return <b>NEEDS_MORE_INFORMATION</b> (which is the
            data-quality gate working as designed).
          </div>

          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => router.push("/")} className="rounded-lg border border-line px-4 py-2 text-sm text-ink2 hover:bg-soft2">Cancel</button>
            <button disabled={!canRun} onClick={run} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-deep disabled:opacity-50">
              <Play size={15} /> Run investigation
            </button>
          </div>
        </Card>
      ) : (
        <Card>
          <div className="flex items-center justify-between">
            <CardLabel>Investigating <span className="mono text-primary-press">{form.id}</span></CardLabel>
            <button onClick={() => router.push("/")} className="text-ink3 hover:text-ink"><X size={18} /></button>
          </div>
          <ol className="mt-3 space-y-1.5">
            {events.map((e, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm">
                <span className="mt-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-green-bg text-green"><Check size={11} /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{e.label}</span>
                    {e.confidence != null && <span className="text-xs text-ink3">{pct(e.confidence)}</span>}
                  </div>
                  {e.message && <div className="truncate text-xs text-ink3">{e.message}</div>}
                </div>
              </li>
            ))}
          </ol>
          {!done && !error && <div className="mt-3 pl-6"><Spinner label="agents working…" /></div>}
          {error && (
            <div className="mt-3 rounded-lg border border-red-border bg-red-bg px-3 py-2 text-sm text-red">
              {error.toLowerCase().includes("fetch") || error.includes("11434")
                ? "Could not reach the backend. Is the API on :8000 and Ollama running?" : error}
            </div>
          )}
          {done && (
            <div className="mt-4 flex justify-end">
              <button onClick={() => router.push(`/case/${encodeURIComponent(done.case_id)}`)} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-deep">
                Open workspace →
              </button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

const inp = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-primary";

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <label className={`block ${full ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-ink3">{label}</span>
      {children}
    </label>
  );
}
