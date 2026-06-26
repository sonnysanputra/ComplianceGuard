import React from "react";

export function Card({
  children,
  className = "",
  pad = true,
}: {
  children: React.ReactNode;
  className?: string;
  pad?: boolean;
}) {
  return (
    <div className={`rounded-2xl border border-line bg-surface shadow-card ${pad ? "p-5" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function CardLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] font-semibold uppercase tracking-wider text-ink3">{children}</div>;
}

type Tone = "green" | "red" | "amber" | "blue" | "violet" | "orange" | "slate";
const TONES: Record<Tone, string> = {
  green: "bg-green-bg text-green border-green-border",
  red: "bg-red-bg text-red border-red-border",
  amber: "bg-amber-bg text-amber border-amber-border",
  blue: "bg-blue-bg text-blue border-blue-border",
  violet: "bg-violet-bg text-violet border-violet-border",
  orange: "bg-primary-soft text-primary-press border-primary-border",
  slate: "bg-soft2 text-ink2 border-line",
};

export function Pill({
  children,
  tone = "slate",
  dot = false,
  className = "",
}: {
  children: React.ReactNode;
  tone?: Tone;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]} ${className}`}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}

export function riskTone(level?: string): Tone {
  const k = (level || "").toUpperCase();
  if (k === "CRITICAL") return "red";
  if (k === "HIGH") return "red";
  if (k === "MEDIUM") return "amber";
  if (k === "LOW") return "green";
  return "slate";
}
export function priorityTone(p?: string): Tone {
  const k = (p || "").toUpperCase();
  if (k === "P1") return "red";
  if (k === "P2") return "amber";
  if (k === "P3") return "blue";
  return "slate";
}
export function statusTone(s?: string): Tone {
  const k = (s || "").toUpperCase();
  if (k.includes("APPROVED")) return "violet";
  if (k.includes("SAR")) return "orange";
  if (k.includes("AWAITING") || k.includes("MANUAL") || k.includes("NEEDS")) return "amber";
  if (k.includes("REJECT") || k.includes("ERROR")) return "red";
  if (k.includes("LOW_RISK") || k.includes("CLEAR")) return "green";
  return "slate";
}
export function prettyStatus(s?: string) {
  return (s || "—").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function RiskBadge({ level }: { level?: string }) {
  return <Pill tone={riskTone(level)} dot>{(level || "—").replace(/\b\w/g, (c) => c.toUpperCase())} Risk</Pill>;
}

export function RiskGauge({ value, level, size = 200 }: { value?: number; level?: string; size?: number }) {
  const v = Math.max(0, Math.min(100, value ?? 0));
  const stroke = 16;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const tone = riskTone(level);
  const color = tone === "red" ? "#dc2626" : tone === "amber" ? "#f59e0b" : tone === "green" ? "#16a34a" : "#9ca3af";
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef2f6" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c - (v / 100) * c}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-5xl font-extrabold" style={{ color }}>{value ?? "—"}</div>
        <div className="text-xs text-ink3">out of 100</div>
      </div>
    </div>
  );
}

export function rm(n?: number | string) {
  if (n === undefined || n === null) return "—";
  const v = typeof n === "string" ? Number(n.replace(/[^\d.-]/g, "")) : n;
  if (Number.isNaN(v)) return String(n);
  return "RM" + v.toLocaleString("en-MY");
}
export function pct(n?: number | null) {
  if (n === undefined || n === null) return "—";
  const v = n <= 1 ? n * 100 : n;
  return `${Math.round(v)}%`;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink2">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line2 border-t-primary" />
      {label}
    </div>
  );
}
