"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  API_BASE, streamInvestigation, extractAlertFromFile, api,
  type Scenario, type StreamProgress, type CustomerProfile, type TxnRow,
} from "@/lib/api";
import { Card, CardLabel, Spinner, pct } from "@/components/ui";
import { Play, Check, X, Upload, FileText, Plus, Trash2, UserPlus, ChevronDown, CheckCircle2, Sparkles } from "lucide-react";

interface Customer { customer_id: string; name?: string; occupation?: string; risk_category?: string }

function genId() {
  const d = new Date();
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  return `AML-${ymd}-${Math.floor(100 + Math.random() * 899)}`;
}

function genCustId() {
  return `CUST-${Math.floor(100000 + Math.random() * 899999)}`;
}

const EMPTY_PROFILE: CustomerProfile = {
  name: "", occupation: "", declared_income: undefined, account_age_months: undefined,
  risk_category: "Medium", previous_alerts: 0, kyc_status: "Completed", country: "Malaysia",
};

export default function NewInvestigation() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [form, setForm] = useState<Scenario>({
    id: genId(), customer_id: "", reason: "", recipient: "",
    country: "Malaysia", total_amount: 0, num_transactions: 1, supporting_document: "",
  });
  const [customerName, setCustomerName] = useState("");
  const [profile, setProfile] = useState<CustomerProfile>(EMPTY_PROFILE);
  const [showProfile, setShowProfile] = useState(false);
  const [txns, setTxns] = useState<TxnRow[]>([]);
  const newIdRef = useRef(genCustId());

  const [running, setRunning] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [events, setEvents] = useState<StreamProgress[]>([]);
  const [done, setDone] = useState<{ case_id: string; status?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState<string | null>(null);
  const [extractErr, setExtractErr] = useState<string | null>(null);
  const startedRef = useRef(false);

  async function onUpload(file: File | undefined) {
    if (!file) return;
    setExtracting(true); setExtractErr(null); setExtracted(null);
    try {
      const a = await extractAlertFromFile(file);
      setForm((f) => ({
        ...f,
        customer_id: a.customer_id || f.customer_id,
        reason: a.reason || f.reason,
        recipient: a.recipient || f.recipient,
        country: a.country || f.country,
        total_amount: a.total_amount || f.total_amount,
        num_transactions: a.num_transactions || f.num_transactions,
        supporting_document: a.supporting_document || file.name,
      }));
      if (a.customer?.name || a.customer_id) setCustomerName(a.customer?.name || a.customer_id);
      if (a.customer) { setProfile({ ...EMPTY_PROFILE, ...a.customer }); setShowProfile(true); }
      if (a.transactions && a.transactions.length) setTxns(a.transactions);
      setExtracted(`${file.name}${a.transactions?.length ? ` — ${a.transactions.length} transactions` : ""}`);
    } catch (e) {
      setExtractErr(e instanceof Error ? e.message : "Could not read that document.");
    } finally {
      setExtracting(false);
    }
  }

  useEffect(() => {
    fetch(`${API_BASE}/customers`, { cache: "no-store" })
      .then((r) => r.json())
      .then((cs: Customer[]) => setCustomers(cs))
      .catch(() => {});
  }, []);

  // Resolve the typed name against existing customers: match -> validated existing
  // customer (use their ID); no match -> a new customer (auto-assign an ID).
  const q = customerName.trim().toLowerCase();
  const matched = q ? customers.find(
    (c) => c.customer_id.toLowerCase() === q || (c.name || "").toLowerCase() === q) : undefined;
  const isExisting = !!matched;
  const resolvedId = matched ? matched.customer_id : newIdRef.current;

  function set<K extends keyof Scenario>(k: K, v: Scenario[K]) { setForm((f) => ({ ...f, [k]: v })); }
  function setP<K extends keyof CustomerProfile>(k: K, v: CustomerProfile[K]) { setProfile((p) => ({ ...p, [k]: v })); }
  function addTxn() {
    setTxns((t) => [...t, { date_time: "", amount: 0, recipient: "", country: form.country || "Malaysia", direction: "out", is_new_recipient: true }]);
  }
  function setTxn(i: number, patch: Partial<TxnRow>) { setTxns((t) => t.map((r, j) => (j === i ? { ...r, ...patch } : r))); }
  function rmTxn(i: number) { setTxns((t) => t.filter((_, j) => j !== i)); }

  const profileFilled = !!(profile.occupation || profile.declared_income || profile.account_age_months);
  const validTxns = txns.filter((t) => Number(t.amount) > 0);

  async function run() {
    if (!customerName.trim() || form.reason.trim().length <= 3 || startedRef.current) return;
    startedRef.current = true;
    setRunning(true); setError(null);

    const alert = { ...form, customer_id: resolvedId };

    // New customer -> always create their profile (at least the name). Existing
    // customer -> only ingest if the analyst added a profile/transactions.
    const wantProfile = !isExisting || profileFilled;
    if (wantProfile || validTxns.length) {
      setIngesting(true);
      try {
        await api.ingest({
          customer_id: resolvedId,
          customer: wantProfile ? { ...profile, name: customerName.trim() } : null,
          transactions: validTxns,
        });
      } catch (e) {
        setIngesting(false); setRunning(false); startedRef.current = false;
        setError(e instanceof Error ? e.message : "Could not save the data to Supabase.");
        return;
      }
      setIngesting(false);
    }

    streamInvestigation(alert, {
      onProgress: (p) => setEvents((e) => [...e, p]),
      onDone: (d) => setDone(d),
      onError: (e) => setError(e),
    });
  }

  const canRun = customerName.trim().length > 1 && form.reason.trim().length > 3;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">New Investigation</h1>
        <p className="text-sm text-ink2">Bring your own customer + transactions (or pick an existing customer), then run the 14-agent investigation live.</p>
      </div>

      {!running ? (
        <Card>
          {/* Upload a document -> auto-fill alert + profile + transactions */}
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-primary-border bg-primary-soft px-4 py-6 text-center transition hover:bg-primary-soft/70">
            <input type="file" accept=".pdf,.docx,.txt,.md,.csv,.eml,.json" className="hidden"
                   onChange={(e) => onUpload(e.target.files?.[0])} disabled={extracting} />
            {extracting ? (
              <Spinner label="reading document & extracting fields…" />
            ) : (
              <>
                <Upload size={22} className="text-primary" />
                <span className="mt-1.5 text-sm font-semibold text-primary-press">Upload an alert or statement</span>
                <span className="text-xs text-ink3">PDF, DOCX, TXT — alert, customer profile &amp; transactions are auto-extracted</span>
              </>
            )}
          </label>
          {extracted && (
            <div className="mt-2 flex items-center gap-2 rounded-lg bg-green-bg px-3 py-2 text-xs text-green">
              <FileText size={14} /> Auto-filled from <b>{extracted}</b> — review and edit below, then run.
            </div>
          )}
          {extractErr && <div className="mt-2 rounded-lg bg-red-bg px-3 py-2 text-xs text-red">{extractErr}</div>}

          <div className="my-4 flex items-center gap-3 text-[11px] uppercase tracking-wider text-ink3">
            <span className="h-px flex-1 bg-line" /> or enter manually <span className="h-px flex-1 bg-line" />
          </div>

          {/* ---- the alert ---- */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Alert ID">
              <input value={form.id} onChange={(e) => set("id", e.target.value)} className={inp} />
            </Field>
            <Field label="Customer name">
              <input list="cg-customers" value={customerName} onChange={(e) => setCustomerName(e.target.value)}
                     placeholder="Search existing or type a new name" className={inp} autoComplete="off" />
              <datalist id="cg-customers">
                {customers.map((c) => (
                  <option key={c.customer_id} value={c.name || c.customer_id}>
                    {c.customer_id}{c.occupation ? ` · ${c.occupation}` : ""}{c.risk_category ? ` · ${c.risk_category} risk` : ""}
                  </option>
                ))}
              </datalist>
              {customerName.trim() && (
                isExisting ? (
                  <span className="mt-1 flex items-center gap-1.5 text-xs text-green">
                    <CheckCircle2 size={13} /> On file — <b className="mono">{matched!.customer_id}</b>
                    {matched!.occupation ? ` · ${matched!.occupation}` : ""}{matched!.risk_category ? ` · ${matched!.risk_category} risk` : ""}
                  </span>
                ) : (
                  <span className="mt-1 flex items-center gap-1.5 text-xs text-ink3">
                    <Sparkles size={13} className="text-primary" /> New customer — ID <b className="mono">{resolvedId}</b> will be created
                  </span>
                )
              )}
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

          {/* ---- customer profile (new customer) ---- */}
          <button onClick={() => setShowProfile((v) => !v)} className="mt-5 flex w-full items-center gap-2 rounded-lg bg-soft px-3 py-2 text-sm font-semibold text-ink2 hover:bg-soft2">
            <UserPlus size={15} className="text-primary" /> Customer profile
            <span className="font-normal text-ink3">— fill this if the customer isn&apos;t on file yet</span>
            <ChevronDown size={15} className={`ml-auto transition ${showProfile ? "rotate-180" : ""}`} />
          </button>
          {showProfile && (
            <div className="mt-3 grid gap-4 rounded-lg border border-line p-4 sm:grid-cols-2">
              <Field label="Occupation"><input value={profile.occupation ?? ""} onChange={(e) => setP("occupation", e.target.value)} className={inp} placeholder="e.g. Junior Clerk" /></Field>
              <Field label="Declared income (RM/month)"><input type="number" value={profile.declared_income ?? ""} onChange={(e) => setP("declared_income", e.target.value ? Number(e.target.value) : undefined)} className={inp} /></Field>
              <Field label="Account age (months)"><input type="number" value={profile.account_age_months ?? ""} onChange={(e) => setP("account_age_months", e.target.value ? Number(e.target.value) : undefined)} className={inp} /></Field>
              <Field label="Risk category">
                <select value={profile.risk_category} onChange={(e) => setP("risk_category", e.target.value)} className={inp}>
                  <option>Low</option><option>Medium</option><option>High</option>
                </select>
              </Field>
              <Field label="Previous alerts"><input type="number" value={profile.previous_alerts ?? 0} onChange={(e) => setP("previous_alerts", Number(e.target.value))} className={inp} /></Field>
            </div>
          )}

          {/* ---- transactions ---- */}
          <div className="mt-5">
            <div className="flex items-center justify-between">
              <CardLabel>Transactions {validTxns.length > 0 && <span className="text-ink3">({validTxns.length})</span>}</CardLabel>
              <button onClick={addTxn} className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold text-ink2 hover:bg-soft2"><Plus size={13} /> Add transaction</button>
            </div>
            <p className="mt-0.5 text-xs text-ink3">These are what the agents actually analyse (typology, timeline, network, baseline). Leave empty to use an existing customer&apos;s history.</p>
            {txns.length > 0 && (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-ink3">
                      <th className="py-1 pr-2 font-semibold">Date / time</th>
                      <th className="py-1 pr-2 font-semibold">Amount</th>
                      <th className="py-1 pr-2 font-semibold">Recipient</th>
                      <th className="py-1 pr-2 font-semibold">Country</th>
                      <th className="py-1 pr-2 font-semibold">Dir.</th>
                      <th className="py-1 pr-2 font-semibold">New?</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {txns.map((t, i) => (
                      <tr key={i}>
                        <td className="py-1 pr-2"><input type="datetime-local" value={(t.date_time || "").slice(0, 16)} onChange={(e) => setTxn(i, { date_time: e.target.value })} className={tcell} /></td>
                        <td className="py-1 pr-2"><input type="number" value={t.amount || ""} onChange={(e) => setTxn(i, { amount: Number(e.target.value) })} className={`${tcell} w-24`} /></td>
                        <td className="py-1 pr-2"><input value={t.recipient ?? ""} onChange={(e) => setTxn(i, { recipient: e.target.value })} className={tcell} placeholder="Beneficiary" /></td>
                        <td className="py-1 pr-2"><input value={t.country ?? ""} onChange={(e) => setTxn(i, { country: e.target.value })} className={`${tcell} w-24`} /></td>
                        <td className="py-1 pr-2">
                          <select value={t.direction} onChange={(e) => setTxn(i, { direction: e.target.value as "in" | "out" })} className={tcell}><option value="out">out</option><option value="in">in</option></select>
                        </td>
                        <td className="py-1 pr-2 text-center"><input type="checkbox" checked={t.is_new_recipient} onChange={(e) => setTxn(i, { is_new_recipient: e.target.checked })} /></td>
                        <td className="py-1"><button onClick={() => rmTxn(i)} className="text-ink3 hover:text-red"><Trash2 size={14} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="mt-4 rounded-lg bg-soft px-3 py-2 text-xs text-ink3">
            Tip: provide transactions (and a profile for a new customer) and they&apos;re saved before the run, so the agents have real data. With no data on file the run returns <b>NEEDS_MORE_INFORMATION</b> — the data-quality gate working as designed.
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
          {ingesting && <div className="mt-3"><Spinner label={`saving ${validTxns.length} transactions${profileFilled ? " + customer profile" : ""}…`} /></div>}
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
          {!done && !error && !ingesting && <div className="mt-3 pl-6"><Spinner label="agents working…" /></div>}
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
const tcell = "rounded-md border border-line bg-surface px-2 py-1 text-xs outline-none focus:border-primary";

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <label className={`block ${full ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-ink3">{label}</span>
      {children}
    </label>
  );
}
