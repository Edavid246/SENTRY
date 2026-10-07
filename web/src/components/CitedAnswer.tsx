"use client";

import type { Citation } from "@/lib/api";

// The model writes citations as [chunk_id: document_title, page N]. Each marker
// is swapped for a badge [DOC-xxx, p.N] that opens the passage in the side panel.
const MARKER = /\[([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})[^\]]*\]/g;

export function citationLabel(c: Citation): string {
  const ref = c.document_ref || c.document_title;
  if (c.page != null) return `${ref}, p.${c.page}`;
  if (c.section) return `${ref}, ${c.section}`;
  return ref;
}

export function CitationBadge({
  citation,
  active,
  onOpen,
}: {
  citation: Citation;
  active: boolean;
  onOpen: (c: Citation) => void;
}) {
  return (
    <button
      type="button"
      data-testid="citation-badge"
      onClick={() => onOpen(citation)}
      title={citation.document_title}
      className={`mx-0.5 inline-block border px-1.5 py-px align-baseline text-[0.8rem] ${
        active
          ? "border-amber bg-amber/10 text-amber"
          : "border-sage/60 text-sage hover:border-amber hover:text-amber"
      }`}
    >
      [{citationLabel(citation)}]
    </button>
  );
}

export function CitedAnswer({
  text,
  citations,
  activeChunkId,
  onOpen,
}: {
  text: string;
  citations: Citation[];
  activeChunkId: string | null;
  onOpen: (c: Citation) => void;
}) {
  const byId = new Map(citations.map((c) => [c.chunk_id.toLowerCase(), c]));
  const used = new Set<string>();
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    const index = m.index ?? 0;
    parts.push(text.slice(last, index));
    const c = byId.get(m[1].toLowerCase());
    if (c) {
      used.add(c.chunk_id);
      parts.push(
        <CitationBadge key={`${index}-${c.chunk_id}`} citation={c} active={c.chunk_id === activeChunkId} onOpen={onOpen} />,
      );
    }
    last = index + m[0].length;
  }
  parts.push(text.slice(last));

  const rest = citations.filter((c) => !used.has(c.chunk_id));
  return (
    <div>
      <p className="whitespace-pre-wrap leading-relaxed">{parts}</p>
      {rest.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1 text-[0.8rem] text-sage">
          <span>Sources</span>
          {rest.map((c) => (
            <CitationBadge key={c.chunk_id} citation={c} active={c.chunk_id === activeChunkId} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
  );
}
