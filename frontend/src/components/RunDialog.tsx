"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { streamInvestigation, toAlert, type Scenario, type StreamProgress } from "@/lib/api";
import { Spinner, pct } from "./ui";
import { Check, X } from "lucide-react";

export default function RunDialog({ scenario, onClose }: { scenario: Scenario; onClose: () => void }) {
  const router = useRouter();
  const [events, setEvents] = useState<StreamProgress[]>([]);
  const [done, setDone] = useState<{ case_id: string; status?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    streamInvestigation(toAlert(scenario), {
      onProgress: (p) => setEvents((e) => [...e, p]),
      onDone: (d) => setDone(d),
      onError: (e) => setError(e),
    });
  }, [scenario]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-cardlg">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div>
            <div className="text-sm font-bold">Investigating <span className="mono text-primary-press">{scenario.id}</span></div>
            <div className="text-xs text-ink3">{scenario.reason}</div>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-ink3 hover:bg-soft2"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <ol className="space-y-1.5">
            {events.map((e, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm">
                <span className="mt-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-green-bg text-green"><Check size={11} /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-ink">{e.label}</span>
                    {e.confidence != null && <span className="shrink-0 text-xs text-ink3">{pct(e.confidence)}</span>}
                  </div>
                  {e.message && <div className="truncate text-xs text-ink3">{e.message}</div>}
                </div>
              </li>
            ))}
          </ol>
          {!done && !error && <div className="mt-3 pl-6"><Spinner label="agents working…" /></div>}
          {error && (
            <div className="mt-3 rounded-lg border border-red-border bg-red-bg px-3 py-2 text-sm text-red">
              {error.includes("11434") || error.toLowerCase().includes("fetch")
                ? "Could not reach the backend. Is the API on :8000 and Ollama running?"
                : error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-line px-5 py-3">
          <div className="text-xs text-ink3">
            {done ? `Done · ${(done.status || "").replaceAll("_", " ")}` : `${events.length} agents completed`}
          </div>
          {done ? (
            <button
              onClick={() => router.push(`/case/${encodeURIComponent(done.case_id)}`)}
              className="rounded-lg bg-primary px-4 py-1.5 text-sm font-semibold text-white hover:bg-primary-deep"
            >
              Open workspace →
            </button>
          ) : (
            <button onClick={onClose} className="rounded-lg border border-line px-4 py-1.5 text-sm text-ink2 hover:bg-soft2">
              Run in background
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
