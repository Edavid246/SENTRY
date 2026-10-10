"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type ComplianceView } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { SectionCard } from "@/components/DivisionSections";

// Certifications and maintenance are background work: this page is where they are all in one
// place. The table counts what needs attention per unit, and each count jumps to its list below;
// every row in the lists opens its record and the evidence behind it.
export default function CompliancePage() {
  const { me } = useSession();
  const [view, setView] = useState<ComplianceView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .compliance()
      .then(setView)
      .catch(() => setError("Compliance could not be loaded."));
  }, [me]);

  // Rows needing attention, counted per owning unit and section.
  const tally = useMemo(() => {
    const units = new Map<string, Record<string, number>>();
    for (const section of view?.sections ?? []) {
      for (const row of section.rows) {
        const counts = units.get(row.unit_name) ?? {};
        counts[section.key] = (counts[section.key] ?? 0) + (row.flagged ? 1 : 0);
        units.set(row.unit_name, counts);
      }
    }
    return [...units.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [view]);

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-5xl">
          <Link href="/home" className="text-[0.9rem] text-sage hover:text-ink">
            ← {me?.unit_breadcrumb[0]?.name ?? "Group"}
          </Link>
          <h1 data-testid="compliance-title" className="mt-6 text-[2rem] font-medium tracking-[0.02em]">
            Compliance
          </h1>
          <p className="mt-1 max-w-[60ch] text-[0.95rem] text-sage">
            Maintenance and certifications across every business you can see. Overdue items come first.
          </p>
          {error && (
            <p role="alert" className="mt-8 border border-rule p-4 text-[0.9rem]">
              {error}
            </p>
          )}
          {!view && !error && <p className="mt-8 text-sage">Loading…</p>}
          {view && (
            <>
              <div className="mt-8 overflow-x-auto border border-rule bg-surface">
                <table data-testid="compliance-tally" className="w-full text-left text-[0.9rem]">
                  <caption className="sr-only">Items needing attention, by unit</caption>
                  <thead>
                    <tr className="border-b border-rule text-[0.8rem] font-normal text-mute">
                      <th scope="col" className="px-5 py-3 font-normal">
                        Unit
                      </th>
                      {view.sections.map((s) => (
                        <th key={s.key} scope="col" className="px-5 py-3 text-right font-normal">
                          {s.key === "maintenance" ? "Maintenance overdue" : "Certifications expired"}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tally.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-5 py-4 text-mute">
                          Nothing is due for maintenance and no certification has expired.
                        </td>
                      </tr>
                    )}
                    {tally.map(([unit, counts]) => (
                      <tr key={unit} className="border-b border-rule last:border-b-0">
                        <th scope="row" className="px-5 py-3 font-normal">
                          {unit}
                        </th>
                        {view.sections.map((s) => {
                          const n = counts[s.key] ?? 0;
                          return (
                            <td key={s.key} className="px-5 py-3 text-right tabular-nums">
                              {n > 0 ? (
                                <a href={`#${s.key}`} className="font-bold text-amber hover:underline">
                                  {n}
                                </a>
                              ) : (
                                <span className="text-mute">0</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-6 grid grid-cols-1 gap-5">
                {view.sections.map((section) => (
                  <SectionCard key={section.key} section={section} showUnit />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}
