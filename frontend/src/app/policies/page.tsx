"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { Card, Pill, Spinner } from "@/components/ui";

interface Policy { policy_id: string; title: string; section?: string; category?: string }

export default function PoliciesPage() {
  const [pols, setPols] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/policies`, { cache: "no-store" })
      .then((r) => r.json()).then(setPols).catch(() => setPols([])).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Policies / RAG Library</h1>
        <p className="text-sm text-ink2">Internal AML policies indexed for retrieval-augmented grounding</p>
      </div>
      <Card pad={false}>
        {loading ? <div className="p-6"><Spinner label="loading policies…" /></div> : (
          <div className="divide-y divide-line">
            {pols.length === 0 && <p className="p-6 text-sm text-ink3">No policies indexed.</p>}
            {pols.map((p) => (
              <div key={p.policy_id} className="flex items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold"><span className="mono text-primary-press">{p.policy_id}</span> · {p.title}</div>
                  <div className="text-xs text-ink3">section {p.section || "—"}</div>
                </div>
                <Pill tone="blue">{p.category || "General"}</Pill>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
