"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  api,
  type DashboardItem,
  type DashboardSummary,
  type DashboardTile,
  type DivisionView,
  type HomeSummary,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { BarList, Findings, TileFrame } from "@/components/DashboardTiles";
import { DivisionGlyph } from "@/components/DivisionGlyph";
import { SectionCard, SerialLookup } from "@/components/DivisionSections";

// Which business an item belongs to: a site team (a unit below a subsidiary) is Field
// Operations; a finding about a site stays with the subsidiary that raised it. Mirrors
// backend/app/api/home.py.
function divisionOf(item: DashboardItem, finding: boolean): string | null {
  const parts = item.unit_path.split("/").filter(Boolean);
  if (parts[0] !== "eib-group" || parts.length < 2) return null;
  if (parts.length >= 3 && !finding) return "field-ops";
  return parts[1];
}

function only(tile: DashboardTile, key: string, finding = false): DashboardTile {
  return { ...tile, items: tile.items.filter((i) => divisionOf(i, finding) === key) };
}

export default function DivisionPage() {
  const { division } = useParams<{ division: string }>();
  const { me, can } = useSession();
  const [running, setRunning] = useState(false);
  const [home, setHome] = useState<HomeSummary | null>(null);
  const [view, setView] = useState<DivisionView | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    Promise.all([api.home(), api.dashboard(), api.division(division).catch(() => null)])
      .then(([h, s, v]) => {
        setHome(h);
        setSummary(s);
        setView(v);
      })
      .catch(() => setError("This business could not be loaded."));
  }, [me, division]);

  async function runCorrelation() {
    setRunning(true);
    try {
      await api.runCorrelation();
      setView(await api.division(division));
    } catch {
      setError("The correlation job could not be run.");
    } finally {
      setRunning(false);
    }
  }

  const current = home?.divisions.find((d) => d.key === division);
  const t = summary?.tiles;

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-5xl">
          {error && (
            <p role="alert" className="border border-rule p-4 text-[0.9rem]">
              {error}
            </p>
          )}
          {!home && !error && <p className="text-sage">Loading…</p>}
          {home && !current && (
            // A business you cannot see reads exactly like one that does not exist.
            <div data-testid="division-not-found">
              <h1 className="text-[1.6rem] font-medium">Not found</h1>
              <p className="mt-2 text-sage">There is no such business, or it is not available to you.</p>
              <Link href="/home" className="btn mt-6 inline-block">
                Back to the group
              </Link>
            </div>
          )}
          {home && current && (
            <>
              <nav aria-label="Businesses" className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[0.9rem]">
                <Link href="/home" data-testid="back-to-group" className="text-sage hover:text-ink">
                  ← {me?.unit_breadcrumb[0]?.name ?? "Group"}
                </Link>
                {home.divisions.map((d) => (
                  <Link
                    key={d.key}
                    href={`/d/${d.key}`}
                    aria-current={d.key === current.key ? "page" : undefined}
                    className={`border-b-2 pb-0.5 ${
                      d.key === current.key
                        ? "border-amber text-amber"
                        : "border-transparent text-sage hover:text-ink"
                    }`}
                  >
                    {d.name}
                    {d.alert && d.key !== current.key && (
                      <span className="ml-1.5 text-amber">{d.alert.count}</span>
                    )}
                  </Link>
                ))}
              </nav>

              <header className="relative mt-8 overflow-hidden border border-rule bg-surface p-6">
                <DivisionGlyph
                  division={current.key}
                  className="pointer-events-none absolute -bottom-6 right-2 h-40 w-40 text-rule"
                />
                <h1 data-testid="division-title" className="relative text-[2rem] font-medium tracking-[0.02em]">
                  {current.name}
                </h1>
                <p className="relative mt-1 text-[0.95rem] text-sage">{current.tagline}</p>
                <p className="relative mt-4 text-[0.9rem]">
                  {current.alert ? (
                    <>
                      <span className="font-bold text-amber">{current.alert.count}</span> need attention:{" "}
                      {current.alert.parts.map((p) => `${p.count} ${p.what}`).join(", ")}
                    </>
                  ) : (
                    <span className="text-sage">Nothing needs attention here.</span>
                  )}
                </p>
              </header>

              {view && view.sections.length > 0 && (
                <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">
                  {view.key === "poctova" && <SerialLookup division={view.key} />}
                  {view.key === "briech" && (
                    <Link
                      href="/map"
                      data-testid="open-map"
                      className="flex items-center justify-between gap-4 border border-rule bg-surface px-4 py-3 text-[0.95rem] hover:border-amber xl:col-span-2"
                    >
                      <span>Open the map: sensors, detections and mission areas</span>
                      <span aria-hidden className="text-amber">→</span>
                    </Link>
                  )}
                  {view.sections.map((section) =>
                    section.key === "findings" ? (
                      <SectionCard
                        key={section.key}
                        section={section}
                        lead
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
                      />
                    ) : (
                      <SectionCard key={section.key} section={section} />
                    ),
                  )}
                  {view.key === "stratoc" && (
                    <Link
                      href="/d/field-ops"
                      data-testid="open-field-ops"
                      className="flex items-center justify-between gap-4 border border-rule bg-surface px-4 py-3 text-[0.95rem] hover:border-amber xl:col-span-2"
                    >
                      <span>Field Operations: the sites and people Stratoc supports</span>
                      <span aria-hidden className="text-amber">→</span>
                    </Link>
                  )}
                </div>
              )}

              {t && !(view && view.sections.length > 0) && (
                <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">
                  {(
                    [
                      ["maintenance_backlog", false],
                      ["overdue_deliveries", false],
                      ["recent_findings", true],
                      ["readiness", false],
                      ["expiring_certifications", false],
                    ] as const
                  ).map(([name, finding]) => {
                    const tile = only(t[name], current.key, finding);
                    if (tile.items.length === 0) return null;
                    return (
                      <TileFrame key={name} tileKey={name} tile={tile}>
                        {name === "recent_findings" ? (
                          <Findings items={tile.items} />
                        ) : (
                          <BarList items={tile.items} />
                        )}
                      </TileFrame>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}
