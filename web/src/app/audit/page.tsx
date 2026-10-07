"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type AuditEvent, type ChainTip, type VerifyReport } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { IconClose, IconLog, IconShieldCheck } from "@/components/Icons";

const str = (v: unknown): string => (typeof v === "string" ? v : v == null ? "—" : String(v));

function DecisionBadge({ value }: { value: string }) {
  const cls =
    value === "allow"
      ? "border-ok text-ok"
      : value === "deny"
        ? "border-bad text-bad"
        : "border-rule text-mute";
  return (
    <span className={`inline-block border px-2 py-0.5 text-[0.75rem] uppercase tracking-[0.1em] ${cls}`}>{value}</span>
  );
}

function StatusLine({ label, ok, tip }: { label: string; ok: boolean | null; tip?: ChainTip | null }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule/60 py-2 last:border-0">
      <span className="text-sage">{label}</span>
      <span className="text-right">
        <span className={ok === true ? "text-ok" : ok === false ? "text-bad" : "text-mute"}>
          {ok === true ? "OK" : ok === false ? "FAILED" : "Not available"}
        </span>
        {tip && <span className="ml-3 text-[0.8rem] text-mute">seq {tip.seq} · {tip.hash.slice(0, 12)}</span>}
      </span>
    </div>
  );
}

function VerifyModal({ report, onClose }: { report: VerifyReport; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-ground/85 p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="verify-title"
        data-testid="verify-modal"
        className="w-full max-w-[560px] border border-rule bg-surface"
      >
        <div className="flex items-center justify-between border-b border-rule px-6 py-4">
          <h2 id="verify-title" className="text-[1.05rem] font-medium tracking-[0.1em]">
            VERIFY CHAIN
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="text-sage hover:text-ink">
            <IconClose size={20} />
          </button>
        </div>
        <div className="px-6 py-5">
          <div
            data-testid="verify-result"
            className={`border px-4 py-3 text-center text-[1rem] font-bold tracking-[0.14em] ${
              report.valid ? "border-ok bg-ok/15 text-ok" : "border-bad bg-bad/15 text-bad"
            }`}
          >
            {report.valid ? "CHAIN VALID" : "CHAIN BROKEN"}
          </div>
          <div className="mt-4 text-[0.9rem]">
            <div className="flex justify-between border-b border-rule/60 py-2">
              <span className="text-sage">Valid</span>
              <span data-testid="verify-valid">{String(report.valid)}</span>
            </div>
            <div className="flex justify-between border-b border-rule/60 py-2">
              <span className="text-sage">Events checked</span>
              <span data-testid="verify-count">{report.checked_count}</span>
            </div>
            <StatusLine label="Checkpoint file" ok={report.checkpoint_ok} tip={report.checkpoint_tip} />
            <StatusLine label="Git ledger" ok={report.ledger_ok} tip={report.ledger_tip} />
            {report.first_bad_event_id && (
              <div className="flex justify-between gap-4 py-2">
                <span className="text-sage">First bad event</span>
                <Link
                  href={`/audit?event_id=${report.first_bad_event_id}`}
                  onClick={onClose}
                  className="text-bad underline"
                  data-testid="first-bad-link"
                >
                  {report.first_bad_event_id.slice(0, 8)}
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function AuditView() {
  const { can } = useSession();
  const params = useSearchParams();
  const focusId = params.get("event_id");

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actor, setActor] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [badId, setBadId] = useState<string | null>(null);

  const allowed = can("read_audit");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.audit(200);
      if (focusId && !list.some((e) => e.event_id === focusId)) {
        const one = await api.audit(1, focusId);
        setEvents([...one, ...list]);
      } else {
        setEvents(list);
      }
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Your role cannot read the audit log."
          : "The audit log could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }, [focusId]);

  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load]);

  useEffect(() => {
    if (!focusId || loading) return;
    document.getElementById(`ev-${focusId}`)?.scrollIntoView({ block: "center" });
  }, [focusId, loading, events]);

  const actors = useMemo(
    () => Array.from(new Set(events.map((e) => str(e.payload.actor)))).sort(),
    [events],
  );
  const shown = actor ? events.filter((e) => str(e.payload.actor) === actor) : events;

  async function verify() {
    setVerifying(true);
    try {
      const r = await api.verify();
      setReport(r);
      setBadId(r.first_bad_event_id);
      setModalOpen(true);
    } catch {
      setError("Verification could not run.");
    } finally {
      setVerifying(false);
    }
  }

  if (!allowed) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <div>
          <h1 className="text-[1.2rem] font-medium">Audit log not available</h1>
          <p className="mt-2 text-sage">Your role cannot read the audit log.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4 p-4">
      <section className="flex min-w-0 flex-1 flex-col border border-rule bg-surface">
        <div className="flex items-center justify-between border-b border-rule px-5 py-3">
          <div className="flex items-center gap-4">
            <IconLog size={28} className="text-sage" />
            <div>
              <h1 className="text-[1.05rem] font-medium tracking-[0.1em]">AUDIT LOG</h1>
              <p className="text-[0.8rem] text-sage">System activity and access log, newest first</p>
            </div>
          </div>
          <button type="button" onClick={() => void load()} className="btn">
            Refresh
          </button>
        </div>

        <div className="flex items-end gap-4 border-b border-rule px-5 py-3">
          <div>
            <label htmlFor="actor" className="label mb-1 block">
              Actor
            </label>
            <select
              id="actor"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              className="field min-w-[220px] py-2"
            >
              <option value="">All actors</option>
              {actors.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {error ? (
            <p role="alert" className="p-6 text-bad">
              {error}
            </p>
          ) : loading ? (
            <p className="p-6 text-sage">Loading audit events…</p>
          ) : (
            <table data-testid="audit-table" className="w-full border-collapse text-left text-[0.85rem]">
              <thead className="sticky top-0 bg-raised">
                <tr className="border-b border-rule">
                  {["Seq", "Timestamp (UTC)", "Actor", "Action", "Resource", "Decision", "Hash"].map((h) => (
                    <th key={h} className="label whitespace-nowrap px-4 py-2.5 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => {
                  const isFocus = e.event_id === focusId;
                  const isBad = e.event_id === badId;
                  const expanded = open === e.event_id;
                  return (
                    <FragmentRow
                      key={e.event_id}
                      e={e}
                      isFocus={isFocus}
                      isBad={isBad}
                      expanded={expanded}
                      onToggle={() => setOpen(expanded ? null : e.event_id)}
                    />
                  );
                })}
                {shown.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-6 text-sage">
                      No events match this actor.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        <div className="border-t border-rule px-5 py-2 text-[0.8rem] text-sage">
          Showing {shown.length} of the {events.length} most recent events
        </div>
      </section>

      <aside className="flex w-[360px] shrink-0 flex-col gap-4">
        <div className="border border-rule bg-surface p-5">
          <div className="flex items-center gap-3">
            <IconShieldCheck size={30} className="text-sage" />
            <div>
              <h2 className="text-[1rem] font-medium tracking-[0.1em]">VERIFY CHAIN</h2>
              <p className="text-[0.8rem] text-sage">Log integrity and chain of custody</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void verify()}
            disabled={verifying}
            className="btn-amber mt-5 w-full"
          >
            {verifying ? "Verifying" : "Verify chain"}
          </button>
          {report && (
            <p className="mt-3 text-[0.8rem] text-sage">
              Last run: {report.valid ? "valid" : "broken"}, {report.checked_count} events.{" "}
              <button type="button" onClick={() => setModalOpen(true)} className="underline hover:text-amber">
                Show details
              </button>
            </p>
          )}
        </div>
        <div className="border border-rule bg-surface p-5 text-[0.85rem] leading-relaxed text-sage">
          Each event stores the hash of the one before it. Any edit, deletion or reordering breaks the chain, and
          verification names the first event that no longer matches.
        </div>
      </aside>

      {report && modalOpen && <VerifyModal report={report} onClose={() => setModalOpen(false)} />}
    </div>
  );
}

function FragmentRow({
  e,
  isFocus,
  isBad,
  expanded,
  onToggle,
}: {
  e: AuditEvent;
  isFocus: boolean;
  isBad: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const decision = str(e.payload.decision);
  const mark = isBad ? "bg-bad/10 outline outline-1 outline-bad" : isFocus ? "bg-amber/10 outline outline-1 outline-amber" : "";
  return (
    <>
      <tr
        id={`ev-${e.event_id}`}
        data-testid="audit-row"
        onClick={onToggle}
        className={`cursor-pointer border-b border-rule/60 hover:bg-raised ${mark}`}
      >
        <td className="whitespace-nowrap px-4 py-2.5 text-sage">{e.seq}</td>
        <td className="whitespace-nowrap px-4 py-2.5">{e.created_at.slice(0, 19).replace("T", " ")}</td>
        <td className="whitespace-nowrap px-4 py-2.5">{str(e.payload.actor)}</td>
        <td className="whitespace-nowrap px-4 py-2.5 uppercase tracking-[0.06em]">{str(e.payload.action)}</td>
        <td className="whitespace-nowrap px-4 py-2.5">{str(e.payload.resource)}</td>
        <td className="px-4 py-2.5">
          <DecisionBadge value={decision} />
        </td>
        <td className="whitespace-nowrap px-4 py-2.5 text-sage">{e.hash.slice(0, 14)}</td>
      </tr>
      {expanded && (
        <tr className="border-b border-rule/60 bg-ground">
          <td colSpan={7} className="px-4 py-3 text-[0.8rem]">
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              <span className="text-sage">Event</span>
              <span className="break-all">{e.event_id}</span>
              <span className="text-sage">Previous hash</span>
              <span className="break-all">{e.prev_hash}</span>
              <span className="text-sage">Hash</span>
              <span className="break-all">{e.hash}</span>
            </div>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap border border-rule p-3 text-sage">
              {JSON.stringify(e.payload, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

export default function AuditPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="p-6 text-sage">Loading…</p>}>
        <AuditView />
      </Suspense>
    </Shell>
  );
}
