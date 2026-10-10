"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type HomeDivision, type HomeSummary } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";
import { DivisionGlyph } from "@/components/DivisionGlyph";

// The card is the whole link. An alert exists only when something needs attention: a quiet
// business shows its name and what it does, nothing more.
function DivisionCard({ division, wide }: { division: HomeDivision; wide?: boolean }) {
  const { alert } = division;
  return (
    <Link
      href={`/d/${division.key}`}
      data-testid={`division-${division.key}`}
      data-alert={alert ? alert.count : 0}
      className={`group relative flex min-h-[210px] overflow-hidden border border-l-[3px] border-rule bg-surface p-7 transition-colors hover:border-sage hover:bg-raised ${
        alert ? "border-l-amber" : "border-l-transparent"
      } ${wide ? "md:col-span-2 md:min-h-[150px]" : ""}`}
    >
      <DivisionGlyph
        division={division.key}
        className="pointer-events-none absolute -bottom-8 -right-6 h-36 w-36 text-rule transition-colors group-hover:text-mute"
      />
      <div className="relative flex w-full flex-col justify-between gap-6">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h2 className="text-[1.7rem] font-medium leading-tight tracking-[0.01em]">
              {division.name}
            </h2>
            <p className="mt-1.5 max-w-[34ch] text-[0.9rem] leading-relaxed text-sage">{division.tagline}</p>
          </div>
          {alert && (
            <div className="text-right">
              <div
                data-testid={`alert-${division.key}`}
                className="font-mono text-[3.4rem] font-bold leading-none text-amber"
              >
                {alert.count}
              </div>
              <div className="mt-1 text-[0.8rem] text-sage">need attention</div>
            </div>
          )}
        </div>
        {!alert && (
          <p className="flex items-center gap-2 text-[0.85rem] text-sage">
            <span aria-hidden className="inline-block h-2 w-2 rounded-full bg-ok" />
            Nothing needs attention
          </p>
        )}
        {alert && (
          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 pr-24">
            <ul className="text-[0.85rem] leading-relaxed text-ink">
              {alert.parts.map((p) => (
                <li key={p.what}>
                  <span className="font-bold text-amber">{p.count}</span> {p.what}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-1.5">
              <ClearanceBadge code={alert.classification} />
              {alert.compartments.map((c) => (
                <span key={c} className="tag">
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}

export default function HomePage() {
  const { me } = useSession();
  const router = useRouter();
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .home()
      .then((s) => {
        // Someone who can see a single business goes straight to it.
        if (s.divisions.length === 1) router.replace(`/d/${s.divisions[0].key}`);
        else setSummary(s);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 403
            ? "Your role has no access to the group home."
            : "The group home could not be loaded.",
        ),
      );
  }, [me, router]);

  const businesses = summary?.divisions.filter((d) => d.key !== "field-ops") ?? [];
  const field = summary?.divisions.find((d) => d.key === "field-ops");

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-5xl">
          <h1 data-testid="home-title" className="text-[2rem] font-medium tracking-[0.02em]">
            {me?.unit_breadcrumb[0]?.name ?? "Group"}
          </h1>
          <p className="mt-1 text-[0.95rem] text-sage">
            Open a business to see what is happening there.
          </p>
          {error && (
            <p role="alert" className="mt-8 border border-rule p-4 text-[0.9rem]">
              {error}
            </p>
          )}
          {!summary && !error && <p className="mt-8 text-sage">Loading…</p>}
          {summary && (
            <div className="mt-8 grid grid-cols-1 gap-5 md:grid-cols-2">
              {businesses.map((d) => (
                <DivisionCard key={d.key} division={d} />
              ))}
              {field && <DivisionCard division={field} wide />}
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}
