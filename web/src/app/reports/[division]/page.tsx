"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, downloadReport, type DivisionReport } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";

// The division report as it will print: a draft with its marking, the same rows as the dashboard,
// and the sources. Nothing here is written by a model; the export carries exactly this.
export default function ReportPage() {
  const { division } = useParams<{ division: string }>();
  const { me } = useSession();
  const [report, setReport] = useState<DivisionReport | null>(null);
  const [state, setState] = useState<"loading" | "missing" | "failed">("loading");
  const [busy, setBusy] = useState<"pdf" | "docx" | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .divisionReport(division)
      .then(setReport)
      // A division you cannot see reads exactly like one that does not exist.
      .catch((err) => setState(err instanceof ApiError && err.status === 404 ? "missing" : "failed"));
  }, [me, division]);

  async function save(format: "pdf" | "docx") {
    setBusy(format);
    setMessage(null);
    try {
      await downloadReport(division, format);
      setMessage(`Exported as ${format.toUpperCase()}. The export is recorded in the audit log.`);
    } catch {
      setMessage("The export failed. Try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Shell>
      <div className="h-full overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-4xl">
          <Link href={`/d/${division}`} className="text-[0.9rem] text-sage hover:text-ink">
            ← Back to the division
          </Link>
          {!report && state === "loading" && <p className="mt-8 text-sage">Loading…</p>}
          {!report && state === "missing" && (
            <div data-testid="report-not-found" className="mt-8">
              <h1 className="text-[1.6rem] font-medium">Not found</h1>
              <p className="mt-2 text-sage">There is no such division, or it is not available to you.</p>
            </div>
          )}
          {!report && state === "failed" && (
            <p role="alert" className="mt-8 border border-rule p-4 text-[0.9rem]">
              The report could not be prepared.
            </p>
          )}
          {report && (
            <>
              <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
                <h1 data-testid="report-title" className="text-[1.8rem] font-medium leading-tight">
                  {report.title}
                </h1>
                <div className="flex gap-3">
                  <button
                    type="button"
                    data-testid="export-pdf"
                    onClick={() => save("pdf")}
                    disabled={busy !== null}
                    className="btn-amber"
                  >
                    {busy === "pdf" ? "Exporting…" : "Export PDF"}
                  </button>
                  <button
                    type="button"
                    data-testid="export-docx"
                    onClick={() => save("docx")}
                    disabled={busy !== null}
                    className="btn"
                  >
                    {busy === "docx" ? "Exporting…" : "Export Word"}
                  </button>
                </div>
              </div>
              <p aria-live="polite" className="mt-2 min-h-[1.25rem] text-[0.85rem] text-sage">
                {message}
              </p>

              <article className="mt-4 border border-rule bg-surface">
                <p
                  data-testid="report-banner"
                  className="border-b border-amber px-6 py-3 text-[0.85rem] font-bold text-amber"
                >
                  {report.banner}
                </p>
                <div className="space-y-6 p-6">
                  <header>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <ClearanceBadge code={report.classification} />
                      {report.compartments.map((c) => (
                        <span key={c} className="tag">
                          {c}
                        </span>
                      ))}
                    </div>
                    <p className="mt-3 text-[0.95rem] text-sage">{report.tagline}</p>
                    <p className="mt-1 text-[0.8rem] text-mute">
                      Generated {report.generated_at} for {report.prepared_for}
                    </p>
                    {report.facts.length > 0 && (
                      <dl className="mt-4 flex flex-wrap gap-x-10 gap-y-3">
                        {report.facts.map(([label, value]) => (
                          <div key={label}>
                            <dt className="text-[0.8rem] text-mute">{label}</dt>
                            <dd className="mt-0.5 text-[1rem]">{value}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </header>

                  <section>
                    <h2 className="text-[1.05rem] font-medium">Summary</h2>
                    <ul data-testid="report-summary" className="mt-2 space-y-1 text-[0.9rem]">
                      {report.summary.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </section>

                  {report.sections.map((section) => (
                    <section key={section.title} data-testid="report-section">
                      <h2 className="text-[1.05rem] font-medium">{section.title}</h2>
                      {section.rows.length === 0 ? (
                        <p className="mt-2 text-[0.85rem] text-mute">{section.empty_text}</p>
                      ) : (
                        <ul className="mt-2 border-t border-rule">
                          {section.rows.map((row) => (
                            <li
                              key={row.ref}
                              className={`border-b border-l-[3px] border-b-rule py-2.5 pl-4 pr-1 ${
                                row.flagged ? "border-l-amber" : "border-l-transparent"
                              }`}
                            >
                              <div className="flex items-baseline justify-between gap-4">
                                <span className={`text-[0.95rem] ${row.flagged ? "text-amber" : ""}`}>
                                  {row.label}
                                </span>
                                <Link
                                  href={`/records/${row.ref}`}
                                  className="shrink-0 text-[0.75rem] tabular-nums text-mute hover:text-ink hover:underline"
                                >
                                  {row.ref}
                                </Link>
                              </div>
                              <p className="mt-0.5 text-[0.85rem] leading-relaxed text-sage">{row.detail}</p>
                            </li>
                          ))}
                        </ul>
                      )}
                      {section.marking && (
                        <p className="mt-1.5 text-[0.75rem] text-mute">Section marking: {section.marking}</p>
                      )}
                    </section>
                  ))}

                  <section>
                    <h2 className="text-[1.05rem] font-medium">Sources</h2>
                    <p className="mt-2 break-words text-[0.8rem] leading-relaxed text-mute">
                      Records: {report.refs.join(", ") || "none"}
                    </p>
                  </section>
                  <p className="text-[0.8rem] text-mute">{report.notice}</p>
                </div>
              </article>
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}
