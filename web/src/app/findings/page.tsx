"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Finding } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";
import { fmtTs } from "@/lib/format";

export default function FindingsPage() {
  const { me, can } = useSession();
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(
    () => api.findings().then(setFindings).catch(() => setError("The findings could not be loaded.")),
    [],
  );

  useEffect(() => {
    if (me) void load();
  }, [me, load]);

  async function run() {
    setRunning(true);
    setError(null);
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
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="label">Findings</h1>
            <p className="mt-1 max-w-2xl text-[0.85rem] text-sage">
              Patterns the system found by connecting separate records. A finding carries the highest
              classification of the records behind it, and each one links to its evidence.
            </p>
          </div>
          {can("run_correlation") && (
            <button type="button" data-testid="run-correlation" onClick={run} disabled={running} className="btn">
              {running ? "Running…" : "Run correlation"}
            </button>
          )}
        </div>
        {error && (
          <p role="alert" className="border border-rule p-4 text-[0.9rem]">
            {error}
          </p>
        )}
        {!findings && !error && <p className="text-sage">Loading…</p>}
        {findings && findings.length === 0 && (
          <p data-testid="no-findings" className="border border-rule p-4 text-sage">
            No findings yet. Run the correlation to look for patterns.
          </p>
        )}
        {findings && findings.length > 0 && (
          <ul data-testid="findings-list" className="max-w-4xl divide-y divide-rule border border-rule bg-surface">
            {findings.map((f) => (
              <li key={f.id} data-testid={`item-${f.id}`} className="px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="border border-bad px-2 py-0.5 text-[0.7rem] uppercase tracking-[0.1em] text-bad">
                    {f.severity}
                  </span>
                  <ClearanceBadge code={f.classification_code} />
                  {f.compartments.map((c) => (
                    <span key={c} className="tag">
                      {c}
                    </span>
                  ))}
                  <span className="ml-auto text-[0.75rem] text-mute">
                    {f.unit_name} · {fmtTs(f.created_at)}
                  </span>
                </div>
                <Link
                  href={`/findings/${encodeURIComponent(f.id)}`}
                  data-testid="finding-link"
                  className="mt-2 block text-[1rem] text-amber hover:underline"
                >
                  {f.title}
                </Link>
                <p className="mt-1 text-[0.85rem] text-sage">{f.summary}</p>
                <p className="mt-1 text-[0.75rem] text-mute">{f.evidence_ids.length} records of evidence</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Shell>
  );
}
