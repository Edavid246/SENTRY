"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type DashboardItem, type DashboardSummary, type DashboardTile } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";
import { Sparkline } from "@/components/Sparkline";

const SEVERITY: Record<string, string> = {
  high: "border-bad text-bad",
  medium: "border-warn text-warn",
  low: "border-sage text-sage",
};

function PlaceholderTag() {
  return (
    <span
      data-testid="placeholder-tag"
      className="border border-warn px-2 py-0.5 text-[0.7rem] uppercase tracking-[0.12em] text-warn"
    >
      Placeholder data
    </span>
  );
}

function TileFrame({
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

function Provenance({ item }: { item: DashboardItem }) {
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

function BarList({ items }: { items: DashboardItem[] }) {
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

function Findings({ items }: { items: DashboardItem[] }) {
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

export default function DashboardPage() {
  const { me, can } = useSession();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(() => {
    return api
      .dashboard()
      .then(setSummary)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 403
            ? "Your role has no access to the dashboard."
            : "The dashboard could not be loaded.",
        ),
      );
  }, []);

  useEffect(() => {
    if (me) void load();
  }, [me, load]);

  async function runCorrelation() {
    setRunning(true);
    try {
      await api.runCorrelation();
      await load();
    } catch {
      setError("The correlation job could not be run.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6">
        <h1 className="label mb-4">Dashboard</h1>
        {error && (
          <p role="alert" className="border border-rule p-4 text-[0.9rem]">
            {error}
          </p>
        )}
        {!summary && !error && <p className="text-sage">Loading…</p>}
        {summary && (
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <TileFrame tileKey="readiness" tile={summary.tiles.readiness}>
              <BarList items={summary.tiles.readiness.items} />
            </TileFrame>
            <TileFrame tileKey="maintenance_backlog" tile={summary.tiles.maintenance_backlog}>
              <BarList items={summary.tiles.maintenance_backlog.items} />
            </TileFrame>
            <TileFrame tileKey="expiring_certifications" tile={summary.tiles.expiring_certifications}>
              <BarList items={summary.tiles.expiring_certifications.items} />
            </TileFrame>
            <TileFrame tileKey="overdue_deliveries" tile={summary.tiles.overdue_deliveries}>
              <BarList items={summary.tiles.overdue_deliveries.items} />
            </TileFrame>
            <TileFrame
              tileKey="recent_findings"
              tile={summary.tiles.recent_findings}
              action={
                can("run_correlation") && (
                  <button
                    type="button"
                    data-testid="run-correlation"
                    onClick={runCorrelation}
                    disabled={running}
                    className="btn"
                  >
                    {running ? "Running…" : "Run correlation"}
                  </button>
                )
              }
            >
              <Findings items={summary.tiles.recent_findings.items} />
            </TileFrame>
          </div>
        )}
      </div>
    </Shell>
  );
}
