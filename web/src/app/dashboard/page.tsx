"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type DashboardSummary } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { BarList, Findings, TileFrame } from "@/components/DashboardTiles";

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
