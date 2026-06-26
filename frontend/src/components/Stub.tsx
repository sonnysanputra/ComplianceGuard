import { Card } from "./ui";

export default function Stub({ title, subtitle, note }: { title: string; subtitle: string; note: string }) {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
        <p className="text-sm text-ink2">{subtitle}</p>
      </div>
      <Card className="flex min-h-48 items-center justify-center text-center">
        <div>
          <div className="text-sm font-semibold text-ink2">{note}</div>
          <p className="mt-1 text-xs text-ink3">Wired to the same backend — coming next.</p>
        </div>
      </Card>
    </div>
  );
}
