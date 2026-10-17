"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type DivisionView, type HomeSummary } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { Page } from "@/components/Page";
import { DivisionGlyph } from "@/components/DivisionGlyph";
import { SectionCard, SerialLookup } from "@/components/DivisionSections";

export default function DivisionPage() {
  const { division } = useParams<{ division: string }>();
  const { me, can } = useSession();
  const [running, setRunning] = useState(false);
  const [home, setHome] = useState<HomeSummary | null>(null);
  const [view, setView] = useState<DivisionView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    Promise.all([api.home(), api.division(division).catch(() => null)])
      .then(([h, v]) => {
        setHome(h);
        setView(v);
      })
      .catch(() => setError("This division could not be loaded."));
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

  // Second-level tabs: a full-width bar under the main tabs, fixed above the scrolling page.
  const bar = home && current && (
    <nav
      aria-label="Divisions"
      className="flex shrink-0 items-center gap-x-6 overflow-x-auto border-b border-rule bg-ground px-6 text-[0.9rem] md:px-8"
    >
      <Link href="/home" data-testid="back-to-group" className="whitespace-nowrap py-3 text-soft hover:text-ink">
        ← {me?.unit_breadcrumb[0]?.name ?? "Group"}
      </Link>
      <span aria-hidden className="h-4 w-px shrink-0 bg-rule" />
      {home.divisions.map((d) => (
        <Link
          key={d.key}
          href={`/d/${d.key}`}
          aria-current={d.key === current.key ? "page" : undefined}
          className={`-mb-px whitespace-nowrap border-b-2 py-3 ${
            d.key === current.key
              ? "border-ink font-medium text-ink"
              : "border-transparent text-soft hover:text-ink"
          }`}
        >
          {d.name}
          {d.alert && d.key !== current.key && (
            <span className="ml-1.5 text-gold">{d.alert.count}</span>
          )}
        </Link>
      ))}
    </nav>
  );

  return (
    <Shell>
      <Page bar={bar}>
        {error && (
          <p role="alert" className="border border-rule p-4 text-[0.9rem]">
            {error}
          </p>
        )}
        {!home && !error && <p className="text-soft">Loading…</p>}
        {home && !current && (
          // A division you cannot see reads exactly like one that does not exist.
          <div data-testid="division-not-found">
            <h1 className="text-[1.6rem] font-medium">Not found</h1>
            <p className="mt-2 text-soft">There is no such division, or it is not available to you.</p>
            <Link href="/home" className="btn mt-6 inline-block">
              Back to the group
            </Link>
          </div>
        )}
        {home && current && (
          <>
            <header className="relative overflow-hidden border border-rule bg-surface p-6">
              <DivisionGlyph
                division={current.key}
                className="pointer-events-none absolute -bottom-6 right-2 h-40 w-40 text-rule"
              />
              <div className="relative flex flex-wrap items-start justify-between gap-4">
                <h1 data-testid="division-title" className="text-[2rem] font-medium tracking-[0.02em]">
                  {current.name}
                </h1>
                {view && view.sections.length > 0 && (
                  <Link href={`/reports/${current.key}`} data-testid="open-report" className="btn">
                    Prepare report
                  </Link>
                )}
              </div>
              <p className="relative mt-1 text-[0.95rem] text-soft">{current.tagline}</p>
              <p className="relative mt-4 max-w-[100ch] pr-24 text-[0.9rem]">
                {current.alert ? (
                  <>
                    <span className="font-bold text-gold">{current.alert.count}</span> need attention:{" "}
                    {current.alert.parts.map((p) => `${p.count} ${p.what}`).join(", ")}
                  </>
                ) : (
                  <span className="text-soft">Nothing needs attention here.</span>
                )}
              </p>
              {view && view.facts.length > 0 && (
                <dl data-testid="division-facts" className="relative mt-5 flex flex-wrap gap-x-10 gap-y-3">
                  {view.facts.map((fact) => (
                    <div key={fact.label}>
                      <dt className="text-[0.8rem] text-mute">{fact.label}</dt>
                      <dd className="mt-0.5 text-[1.05rem]">{fact.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </header>

            {view && view.sections.length > 0 && (
              <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">
                {view.key === "poctova" && <SerialLookup division={view.key} />}
                {view.key === "briech" && (
                  <Link
                    href="/map"
                    data-testid="open-map"
                    className="flex items-center justify-between gap-4 border border-rule bg-surface px-4 py-3 text-[0.95rem] hover:border-accent xl:col-span-2"
                  >
                    <span>Open the map: sensors, detections and mission areas</span>
                    <span aria-hidden className="text-accent">→</span>
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
                    className="flex items-center justify-between gap-4 border border-rule bg-surface px-4 py-3 text-[0.95rem] hover:border-accent xl:col-span-2"
                  >
                    <span>Field Operations: the sites and people Stratoc supports</span>
                    <span aria-hidden className="text-accent">→</span>
                  </Link>
                )}
              </div>
            )}

          </>
        )}
      </Page>
    </Shell>
  );
}
