"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError, type DivisionSection } from "@/lib/api";
import { ClearanceBadge } from "./ClearanceBadge";

// How much of a service interval has been flown. The tick marks the last tenth, where an
// aircraft should already be booked in; the fill turns amber once it passes the tick.
function ServiceGauge({ fraction }: { fraction: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
  return (
    <div
      role="meter"
      aria-label="Service interval flown"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      data-testid="service-gauge"
      className="relative mt-2 h-2 border border-rule bg-ground"
    >
      <div className={`h-full ${pct >= 90 ? "bg-amber" : "bg-sage"}`} style={{ width: `${pct}%` }} />
      <span aria-hidden className="absolute inset-y-[-3px] left-[90%] w-px bg-ink opacity-60" />
    </div>
  );
}

// One section of a division dashboard: the rows of a typed tool, each linking to its record
// (and from there to the evidence panel). Flagged rows are the ones needing attention.
export function SectionCard({
  section,
  action,
  lead = false,
}: {
  section: DivisionSection;
  action?: React.ReactNode;
  lead?: boolean;
}) {
  return (
    <section
      data-testid={`section-${section.key}`}
      className={`border bg-surface ${lead ? "border-amber xl:col-span-2" : "border-rule"}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-4 py-3">
        <h2 className="label">{section.title}</h2>
        <span className="flex items-center gap-4 font-mono text-[0.85rem]">
          {action}
          {section.flagged > 0 ? (
            <span className="text-amber">{section.flagged} need attention</span>
          ) : (
            <span className="text-sage">{section.rows.length}</span>
          )}
        </span>
      </header>
      <div className="p-4">
        {section.rows.length === 0 ? (
          <p className="text-[0.85rem] text-mute">{section.empty_text}</p>
        ) : (
          <ul className="divide-y divide-rule">
            {section.rows.map((row) => (
              <li key={row.ref} className="py-3 first:pt-0 last:pb-0">
                <Link
                  href={row.href}
                  data-testid="row-link"
                  className={`block hover:underline ${lead ? "text-[1.2rem] font-medium" : "text-[0.95rem]"} ${row.flagged ? "text-amber" : ""}`}
                >
                  {row.label}
                </Link>
                <p className="mt-1 text-[0.85rem] text-sage">{row.detail}</p>
                {row.meter != null && <ServiceGauge fraction={row.meter} />}
                <p className="mt-1 font-mono text-[0.7rem] text-mute">{row.ref}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t border-rule px-4 py-2 text-[0.7rem] text-mute">
        <span>Tool: {section.tool}</span>
        {section.classification && <ClearanceBadge code={section.classification} />}
        {section.compartments.map((c) => (
          <span key={c} className="tag">
            {c}
          </span>
        ))}
      </footer>
    </section>
  );
}

// Look up one serial number: its run, QC state and delivery. A serial you cannot see answers
// exactly like one that does not exist.
export function SerialLookup({ division }: { division: string }) {
  const [serial, setSerial] = useState("");
  const [result, setResult] = useState<DivisionSection | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function lookup(e: React.FormEvent) {
    e.preventDefault();
    const value = serial.trim().toUpperCase();
    if (!value) return;
    setMessage(null);
    try {
      setResult(await api.serialTrace(division, value));
    } catch (err) {
      setResult(null);
      setMessage(
        err instanceof ApiError && err.status === 422
          ? "That is not a valid serial number, for example PCT-ARM-0007."
          : "The lookup failed.",
      );
    }
  }

  return (
    <section data-testid="serial-lookup" className="border border-rule bg-surface">
      <header className="border-b border-rule px-4 py-3">
        <h2 className="label">Trace a serial number</h2>
      </header>
      <div className="p-4">
        <form onSubmit={lookup} className="flex flex-wrap gap-3">
          <input
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            aria-label="Serial number"
            placeholder="PCT-ARM-0007"
            maxLength={20}
            className="min-w-0 flex-1 border border-rule bg-ground px-3 py-2 font-mono text-[0.9rem]"
          />
          <button type="submit" className="btn">
            Trace
          </button>
        </form>
        {message && (
          <p role="alert" className="mt-3 text-[0.85rem] text-bad">
            {message}
          </p>
        )}
        {result &&
          (result.rows.length === 0 ? (
            <p data-testid="trace-none" className="mt-3 text-[0.85rem] text-mute">
              {result.empty_text}
            </p>
          ) : (
            <ul className="mt-3">
              {result.rows.map((row) => (
                <li key={row.ref} data-testid="trace-row">
                  <Link
                    href={`/records/${encodeURIComponent(row.ref)}`}
                    className="text-[0.95rem] hover:underline"
                  >
                    {row.label}
                  </Link>
                  <p className="mt-1 text-[0.85rem] text-sage">{row.detail}</p>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </section>
  );
}
