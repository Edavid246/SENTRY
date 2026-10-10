"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type CaseView } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";

type Evidence = CaseView["evidence"][number];

// One evidence item and its chain of custody, oldest first. Each hand-over is a point on a
// vertical line. A break is a hand-over whose recorded holder is not whoever last received the
// item; it sits on an amber point with the name that was expected, so the gap reads at a glance.
function Custody({ item }: { item: Evidence }) {
  const broken = item.steps.filter((s) => s.expected_holder).length;
  return (
    <section data-testid={`evidence-${item.evidence_ref}`} className="border border-rule bg-surface">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-rule px-5 py-3.5">
        <h3 className="text-[1rem] font-medium">
          <Link href={`/records/${item.ref}`} className="hover:underline">
            {item.evidence_ref} · {item.item}
          </Link>
        </h3>
        <span className="text-[0.85rem] text-sage">
          {item.kind} · {item.status}
        </span>
      </header>
      <ol className="px-5 py-4">
        {item.steps.map((step, i) => {
          const gap = Boolean(step.expected_holder);
          return (
            <li key={step.ref} data-testid={gap ? "custody-break" : "custody-step"} className="relative pb-5 pl-7 last:pb-0">
              {i < item.steps.length - 1 && (
                <span aria-hidden className="absolute bottom-0 left-[5px] top-3 w-px bg-rule" />
              )}
              <span
                aria-hidden
                className={`absolute left-0 top-1.5 h-[11px] w-[11px] ${gap ? "bg-amber" : "border border-sage bg-ground"}`}
              />
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <Link href={`/records/${step.ref}`} className={`text-[0.95rem] hover:underline ${gap ? "text-amber" : ""}`}>
                  {step.action}
                </Link>
                <span className="text-[0.8rem] tabular-nums text-mute">{step.event_date}</span>
              </div>
              <p className="mt-0.5 text-[0.85rem] text-sage">
                {step.from_holder} → {step.to_holder}
              </p>
              {gap && (
                <p className="mt-1 text-[0.85rem] text-amber">
                  Break: the last holder on record was {step.expected_holder}, not {step.from_holder}.
                </p>
              )}
            </li>
          );
        })}
      </ol>
      <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule px-5 py-2 text-[0.7rem] text-mute">
        <span className="font-mono" title="Synthetic hash, not of any real content">
          sha256 {item.sha256.slice(0, 16)}…
        </span>
        <span>{item.steps.length} custody events</span>
        {broken > 0 && <span className="text-amber">{broken} break</span>}
      </footer>
    </section>
  );
}

export default function CasePage() {
  const { ref } = useParams<{ ref: string }>();
  const { me } = useSession();
  const [view, setView] = useState<CaseView | null>(null);
  const [state, setState] = useState<"loading" | "missing" | "failed">("loading");

  useEffect(() => {
    if (!me) return;
    api
      .forensicCase(ref)
      .then(setView)
      // A case you cannot see reads exactly like one that does not exist.
      .catch((err) => setState(err instanceof ApiError && err.status === 404 ? "missing" : "failed"));
  }, [me, ref]);

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-5xl">
          <Link href="/d/giga" className="text-[0.9rem] text-sage hover:text-ink">
            ← Giga Forensics
          </Link>
          {!view && state === "loading" && <p className="mt-8 text-sage">Loading…</p>}
          {!view && state === "missing" && (
            <div data-testid="case-not-found" className="mt-8">
              <h1 className="text-[1.6rem] font-medium">Not found</h1>
              <p className="mt-2 text-sage">There is no such case, or it is not available to you.</p>
            </div>
          )}
          {!view && state === "failed" && (
            <p role="alert" className="mt-8 border border-rule p-4 text-[0.9rem]">
              The case could not be loaded.
            </p>
          )}
          {view && (
            <>
              <header className="mt-6 border border-rule bg-surface p-6">
                <p className="text-[0.85rem] text-sage">{view.case_ref}</p>
                <h1 data-testid="case-title" className="mt-1 text-[1.8rem] font-medium leading-tight">
                  {view.title}
                </h1>
                <p className="mt-3 text-[0.9rem]">
                  {view.breaks > 0 ? (
                    <>
                      <span className="font-bold text-amber">{view.breaks}</span> custody{" "}
                      {view.breaks === 1 ? "break" : "breaks"} to explain
                    </>
                  ) : (
                    <span className="text-sage">Every chain of custody is unbroken.</span>
                  )}
                </p>
                <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-3">
                  {[
                    ["Status", view.state],
                    ["Opened", view.opened],
                    ["Lead examiner", view.lead_examiner],
                    ["Evidence items", String(view.evidence.length)],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-[0.8rem] text-mute">{label}</dt>
                      <dd className="mt-0.5 text-[1.05rem]">{value}</dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-5 flex flex-wrap items-center gap-1.5">
                  <ClearanceBadge code={view.classification} />
                  {view.compartments.map((c) => (
                    <span key={c} className="tag">
                      {c}
                    </span>
                  ))}
                  <Link href={`/records/${view.ref}`} className="ml-3 text-[0.85rem] text-sage hover:text-ink hover:underline">
                    Case record {view.ref}
                  </Link>
                  <Link href="/audit" className="ml-3 text-[0.85rem] text-sage hover:text-ink hover:underline">
                    Audit log
                  </Link>
                </div>
              </header>
              <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">
                {view.evidence.map((item) => (
                  <Custody key={item.ref} item={item} />
                ))}
              </div>
              <p className="mt-6 max-w-[62ch] text-[0.8rem] text-mute">
                Demo data. The assistant only reports what the records say; deciding what a break means
                is a person&apos;s job.
              </p>
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}
