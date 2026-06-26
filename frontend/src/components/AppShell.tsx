"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FolderOpen, ScanSearch, BookOpen, BarChart3,
  ScrollText, Settings, Bell, Sun, ChevronLeft, Plus,
} from "lucide-react";

const NAV = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard, match: (p: string) => p === "/" },
  { label: "Cases", href: "/cases", icon: FolderOpen, match: (p: string) => p === "/cases" },
  { label: "Investigation Workspace", href: "/workspace", icon: ScanSearch, match: (p: string) => p.startsWith("/case/") || p.startsWith("/workspace") },
  { label: "Policies / RAG Library", href: "/policies", icon: BookOpen, match: (p: string) => p.startsWith("/policies") },
  { label: "Analytics", href: "/analytics", icon: BarChart3, match: (p: string) => p.startsWith("/analytics") },
  { label: "Audit Logs", href: "/audit", icon: ScrollText, match: (p: string) => p.startsWith("/audit") },
  { label: "Settings", href: "/settings", icon: Settings, match: (p: string) => p.startsWith("/settings") },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-surface md:flex">
        <Link href="/" className="block px-5 pb-2 pt-5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="ComplianceGuard" className="w-[172px]" />
          <div className="mt-1 pl-1 text-[11px] text-ink3">AML Investigation Suite</div>
        </Link>

        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map((n) => {
            const active = n.match(path);
            const Icon = n.icon;
            return (
              <Link
                key={n.label}
                href={n.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-primary-soft text-primary-press"
                    : "text-ink2 hover:bg-soft2 hover:text-ink"
                }`}
              >
                <Icon size={18} className={active ? "text-primary" : "text-ink3"} />
                {n.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-line p-3">
          <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink2 hover:bg-soft2">
            <ChevronLeft size={16} /> Collapse
          </button>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-20 border-b border-line bg-surface/85 backdrop-blur">
          <div className="flex items-center gap-3 px-6 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-soft2 text-ink2">
                <LayoutDashboard size={15} />
              </div>
              <div className="leading-tight">
                <div className="text-[13px] font-semibold">Meridian Digital Bank</div>
                <div className="text-[11px] text-ink3">AML Operations</div>
              </div>
            </div>

            <Link
              href="/new"
              className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white shadow-card hover:bg-primary-deep"
            >
              <Plus size={16} /> New Investigation
            </Link>
            <button className="rounded-lg border border-line p-2 text-ink2 hover:bg-soft2"><Bell size={16} /></button>
            <button className="rounded-lg border border-line p-2 text-ink2 hover:bg-soft2"><Sun size={16} /></button>
            <div className="flex items-center gap-2 pl-1">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary-press">SL</div>
              <div className="hidden leading-tight sm:block">
                <div className="text-[13px] font-semibold">Sarah Lim</div>
                <div className="text-[11px] text-ink3">Senior Compliance Analyst</div>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
