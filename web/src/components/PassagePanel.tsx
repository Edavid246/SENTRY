"use client";

import type { Chunk, Citation } from "@/lib/api";
import { ClearanceBadge } from "./ClearanceBadge";
import { citationLabel } from "./CitedAnswer";
import { IconClose } from "./Icons";

export type PanelState =
  | { status: "loading"; citation: Citation }
  | { status: "ok"; citation: Citation; chunk: Chunk }
  | { status: "missing"; citation: Citation };

export function PassagePanel({ state, onClose }: { state: PanelState; onClose: () => void }) {
  return (
    <aside
      data-testid="passage-panel"
      aria-label="Cited passage"
      className="flex w-[440px] shrink-0 flex-col border-l border-rule bg-surface"
    >
      <div className="flex items-center justify-between border-b border-rule px-5 py-3">
        <div>
          <div className="label">Cited passage</div>
          <div className="text-[0.9rem] text-amber">{citationLabel(state.citation)}</div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close passage" className="text-sage hover:text-ink">
          <IconClose size={20} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {state.status === "loading" && <p className="text-sage">Loading passage…</p>}
        {state.status === "missing" && (
          <p className="text-sage">This passage is not available to your clearance.</p>
        )}
        {state.status === "ok" && (
          <>
            <h2 className="text-[1rem] font-medium">{state.chunk.document_title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <ClearanceBadge code={state.chunk.classification_code} />
              {state.chunk.compartments.map((c) => (
                <span key={c} className="tag">
                  {c}
                </span>
              ))}
            </div>
            <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[0.85rem]">
              <dt className="text-sage">Document</dt>
              <dd>{state.chunk.document_ref || "—"}</dd>
              <dt className="text-sage">Page</dt>
              <dd>{state.chunk.page ?? "—"}</dd>
              <dt className="text-sage">Section</dt>
              <dd>{state.chunk.section ?? "—"}</dd>
            </dl>
            <blockquote className="mt-4 whitespace-pre-wrap border-l-2 border-rule pl-4 leading-relaxed">
              {state.chunk.text}
            </blockquote>
          </>
        )}
      </div>
    </aside>
  );
}
