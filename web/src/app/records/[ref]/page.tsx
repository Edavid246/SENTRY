"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type RecordDetail } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function RecordPage() {
  const { me } = useSession();
  const params = useParams<{ ref: string }>();
  const ref = decodeURIComponent(params.ref);
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .record(ref)
      .then(setRecord)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Record not found, or not available to you."
            : "The record could not be loaded.",
        ),
      );
  }, [me, ref]);

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6">
        <Link href="/chat" className="label hover:text-ink">
          ← Back to assistant
        </Link>
        <h1 className="mt-3 font-mono text-[1.3rem]">{ref}</h1>
        {error && (
          <p role="alert" data-testid="record-error" className="mt-4 border border-rule p-4">
            {error}
          </p>
        )}
        {!record && !error && <p className="mt-4 text-sage">Loading…</p>}
        {record && (
          <div data-testid="record-detail" className="mt-4 max-w-3xl border border-rule bg-surface">
            <div className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-3">
              <span className="label">{record.entity_type}</span>
              <ClearanceBadge code={record.classification_code} />
              {record.compartments.map((c) => (
                <span key={c} className="tag">
                  {c}
                </span>
              ))}
            </div>
            <dl className="grid grid-cols-[12rem_1fr] gap-x-4 gap-y-2 px-4 py-4 text-[0.9rem]">
              <dt className="text-mute">Source system</dt>
              <dd>{record.source_system}</dd>
              <dt className="text-mute">Owning unit</dt>
              <dd className="font-mono">{record.unit_path}</dd>
              <dt className="text-mute">Retrieved</dt>
              <dd className="font-mono">{record.retrieved_at}</dd>
              {Object.entries(record.data).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-mute">{key.replaceAll("_", " ")}</dt>
                  <dd>{show(value)}</dd>
                </div>
              ))}
            </dl>
            <div className="border-t border-rule px-4 py-2 text-[0.75rem] text-mute">
              Read-only view of the demo reference system · fictitious data
            </div>
          </div>
        )}
      </div>
    </Shell>
  );
}
