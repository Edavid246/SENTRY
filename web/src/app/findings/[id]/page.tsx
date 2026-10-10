"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type Finding } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";
import { BackLink } from "@/components/BackLink";

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function FindingPage() {
  const { me } = useSession();
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .finding(id)
      .then(setFinding)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Finding not found, or not available to you."
            : "The finding could not be loaded.",
        ),
      );
  }, [me, id]);

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6">
        <BackLink fallback="/dashboard" />
        {error && (
          <p role="alert" data-testid="finding-error" className="mt-4 border border-rule p-4">
            {error}
          </p>
        )}
        {!finding && !error && <p className="mt-4 text-sage">Loading…</p>}
        {finding && (
          <div data-testid="finding-detail" className="mt-4 max-w-4xl border border-rule bg-surface">
            <div className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-3">
              <span className="border border-bad px-2 py-0.5 text-[0.7rem] uppercase tracking-[0.1em] text-bad">
                {finding.severity}
              </span>
              <ClearanceBadge code={finding.classification_code} />
              {finding.compartments.map((c) => (
                <span key={c} className="tag">
                  {c}
                </span>
              ))}
              <span className="text-[0.75rem] text-mute">{finding.unit_name}</span>
              <span className="ml-auto font-mono text-[0.75rem] text-mute">{finding.id}</span>
            </div>
            <div className="px-4 py-4">
              <h1 className="text-[1.15rem]">{finding.title}</h1>
              <p className="mt-2 text-[0.95rem] text-sage">{finding.summary}</p>
              <p className="mt-2 text-[0.75rem] text-mute">
                Derived item: it carries the highest classification and the union of compartments of
                its evidence.
              </p>
            </div>
            <div className="border-t border-rule px-4 py-4">
              <h2 className="label mb-2">Evidence ({finding.evidence_ids.length})</h2>
              <ul data-testid="evidence-list" className="flex flex-wrap gap-2">
                {finding.evidence_ids.map((ref) => (
                  <li key={ref}>
                    <Link
                      href={`/records/${encodeURIComponent(ref)}`}
                      data-testid="evidence-link"
                      className="tag text-amber hover:underline"
                    >
                      {ref}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div className="border-t border-rule px-4 py-4">
              <h2 className="label mb-2">Analysis</h2>
              <dl className="grid grid-cols-1 gap-x-4 gap-y-1 md:grid-cols-[14rem_1fr] md:gap-y-2 text-[0.85rem]">
                <dt className="text-mute">analysis</dt>
                <dd className="font-mono">{finding.analysis}</dd>
                {Object.entries(finding.details).map(([key, value]) => (
                  <div key={key} className="contents">
                    <dt className="text-mute">{key.replaceAll("_", " ")}</dt>
                    <dd>{show(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="border-t border-rule px-4 py-2 text-[0.75rem] text-mute">
              Computed from the typed tools and the demo reference adapter · fictitious data
            </div>
          </div>
        )}
      </div>
    </Shell>
  );
}
