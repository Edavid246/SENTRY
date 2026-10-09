import Link from "next/link";
import type { DashboardItem, DashboardTile } from "@/lib/api";
import { ClearanceBadge } from "./ClearanceBadge";
import { Sparkline } from "./Sparkline";

const SEVERITY: Record<string, string> = {
  high: "border-bad text-bad",
  medium: "border-warn text-warn",
  low: "border-sage text-sage",
};

export function PlaceholderTag() {
  return (
    <span
      data-testid="placeholder-tag"
      className="border border-warn px-2 py-0.5 text-[0.7rem] uppercase tracking-[0.12em] text-warn"
    >
      Placeholder data
    </span>
  );
}

export function TileFrame({
  tileKey,
  tile,
  action,
  children,
}: {
  tileKey: string;
  tile: DashboardTile;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section data-testid={`tile-${tileKey}`} className="border border-rule bg-surface">
      <header className="flex items-center justify-between border-b border-rule px-4 py-3">
        <h2 className="label">{tile.title}</h2>
        <div className="flex items-center gap-3">
          {action}
          {tile.stub && <PlaceholderTag />}
        </div>
      </header>
      <div className="p-4">
        {tile.items.length === 0 ? <p className="text-[0.85rem] text-mute">No items.</p> : children}
      </div>
      <footer className="border-t border-rule px-4 py-2 text-[0.7rem] text-mute">
        Source: {tile.source}
      </footer>
    </section>
  );
}

export function Provenance({ item }: { item: DashboardItem }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-[0.7rem] text-mute">
      <ClearanceBadge code={item.classification} />
      {item.compartments.map((c) => (
        <span key={c} className="tag">
          {c}
        </span>
      ))}
      <span>{item.unit_name}</span>
    </div>
  );
}

export function BarList({ items }: { items: DashboardItem[] }) {
  const percent = items.every((i) => i.unit === "%");
  const max = percent ? 100 : Math.max(10, ...items.map((i) => i.value ?? 0));
  return (
    <ul className="space-y-4">
      {items.map((item) => {
        const pct = Math.max(0, Math.min(100, ((item.value ?? 0) / max) * 100));
        const warn = item.severity === "medium" || item.severity === "high";
        return (
          <li key={item.id} data-testid={`item-${item.id}`}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-[0.9rem]">
              <span>{item.label}</span>
              <span className="font-mono">
                {item.value}
                {item.unit === "%" ? "%" : ` ${item.unit ?? ""}`}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="h-2 flex-1 border border-rule bg-ground">
                <div className={`h-full ${warn ? "bg-warn" : "bg-sage"}`} style={{ width: `${pct}%` }} />
              </div>
              <Sparkline values={item.trend} />
            </div>
            <Provenance item={item} />
          </li>
        );
      })}
    </ul>
  );
}

export function Findings({ items }: { items: DashboardItem[] }) {
  return (
    <ul className="divide-y divide-rule">
      {items.map((item) => (
        <li key={item.id} data-testid={`item-${item.id}`} className="py-3 first:pt-0 last:pb-0">
          {item.severity && (
            <span
              className={`mb-1 inline-block border px-2 py-0.5 text-[0.7rem] uppercase tracking-[0.1em] ${SEVERITY[item.severity] ?? "border-rule text-sage"}`}
            >
              {item.severity}
            </span>
          )}
          <Link
            href={`/findings/${encodeURIComponent(item.id)}`}
            data-testid="finding-link"
            className="block text-[0.95rem] text-amber hover:underline"
          >
            {item.label}
          </Link>
          <p className="mt-1 text-[0.85rem] text-sage">{item.detail}</p>
          <Provenance item={item} />
        </li>
      ))}
    </ul>
  );
}
