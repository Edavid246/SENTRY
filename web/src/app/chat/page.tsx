"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Citation, type ConversationSummary, type ReportInfo, type ResultTable } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { CitedAnswer } from "@/components/CitedAnswer";
import { ClearanceBadge } from "@/components/ClearanceBadge";
import { ResultTableView } from "@/components/ResultTableView";
import { PassagePanel, type PanelState } from "@/components/PassagePanel";
import { IconArrow, IconPlus } from "@/components/Icons";

interface Meta {
  report?: ReportInfo | null;
  found: boolean;
  degraded: boolean;
  refused: boolean;
  table: ResultTable | null;
  auditEventId: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  meta?: Meta;
  error?: boolean;
  /** Calm "recorded answers only" panel: model unavailable or no answer within the wait limit. */
  notice?: boolean;
}

// The demonstration answers its scripted questions from recorded answers. When the
// model is unreachable (503: nothing recorded for the question) or silent for too
// long, say so calmly; never show a raw error or wait forever.
const NOTICE_TEXT =
  "This demonstration runs on recorded answers for its scripted questions. " +
  "Live model access is disabled in this environment.";
const ASK_TIMEOUT_MS = 30_000;

const STARTERS = [
  "Find the documents relating to the vehicle maintenance policy and summarize the key requirements.",
  "Show me the equipment currently awaiting maintenance.",
  "Prepare a summary of training activity for this group over the last quarter.",
  "Which deliveries are overdue?",
  "Trace serial BRC-0041.",
];

let counter = 0;
const nextId = () => `m${++counter}`;

function Thread({
  messages,
  pending,
  elapsed,
  activeChunkId,
  onOpen,
  onStarter,
  canAudit,
  canAsk,
}: {
  messages: Message[];
  pending: boolean;
  elapsed: number;
  activeChunkId: string | null;
  onOpen: (c: Citation) => void;
  onStarter: (q: string) => void;
  canAudit: boolean;
  canAsk: boolean;
}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, pending]);

  if (!messages.length && !pending) {
    return (
      <div className="flex flex-1 flex-col justify-center px-10">
        {canAsk ? (
          <div className="mx-auto w-full max-w-[760px]">
            <h1 className="text-[1.25rem] font-medium tracking-[0.06em]">Ask about approved sources</h1>
            <p className="mt-2 text-sage">
              You only see answers built from material you are cleared for. Every question is logged.
            </p>
            <div className="mt-6 flex flex-col gap-2">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => onStarter(q)}
                  className="border border-rule bg-surface px-4 py-3 text-left text-[0.95rem] hover:border-amber"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-[620px] text-center">
            <h1 className="text-[1.25rem] font-medium">This role has no assistant access</h1>
            <p className="mt-2 text-sage">
              Your account can review the audit log only.{" "}
              {canAudit && (
                <Link href="/audit" className="text-amber underline">
                  Open the audit log
                </Link>
              )}
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
      <div className="mx-auto flex max-w-[860px] flex-col gap-5">
        {messages.map((m) => (
          <article
            key={m.id}
            data-testid={`msg-${m.role}`}
            className={`border ${m.role === "user" ? "border-rule bg-raised" : "border-rule bg-surface"}`}
          >
            <div className="flex items-center justify-between border-b border-rule px-4 py-1.5">
              <span className="label">{m.role === "user" ? "You" : "Assistant"}</span>
              {m.meta?.degraded && (
                <span data-testid="degraded-note" className="text-[0.75rem] text-sage">
                  Keyword search only
                </span>
              )}
            </div>
            <div className="px-4 py-3">
              {m.meta?.report && (
                <div
                  data-testid="draft-banner"
                  className="mb-3 flex flex-wrap items-center gap-2 border border-amber bg-amber/10 px-3 py-2 text-[0.85rem] font-medium uppercase tracking-[0.1em] text-amber"
                >
                  Draft for human review
                  <ClearanceBadge code={m.meta.report.classification_code} />
                  {m.meta.report.compartments.map((c) => (
                    <span key={c} className="tag">
                      {c}
                    </span>
                  ))}
                </div>
              )}
              {m.meta?.refused && (
                <div
                  role="alert"
                  data-testid="refused-banner"
                  className="mb-3 border border-bad bg-bad/10 px-3 py-2 text-[0.9rem] font-medium text-bad"
                >
                  Request refused — logged
                </div>
              )}
              {m.notice ? (
                <div data-testid="demo-notice" role="status" className="border border-rule bg-raised px-4 py-3">
                  <p className="leading-relaxed">{m.content}</p>
                  <p className="mt-2 text-[0.8rem] text-mute">
                    Try one of the scripted questions. Your request and its access decision were logged.
                  </p>
                </div>
              ) : m.error ? (
                <p role="alert" className="text-bad">
                  {m.content}
                </p>
              ) : m.role === "assistant" ? (
                <CitedAnswer text={m.content} citations={m.citations} activeChunkId={activeChunkId} onOpen={onOpen} />
              ) : (
                <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
              )}
              {m.meta && !m.meta.found && !m.meta.refused && !m.error && (
                <p data-testid="not-found-note" className="mt-3 text-[0.85rem] text-mute">
                  No information found in approved sources
                </p>
              )}
              {m.meta?.table && <ResultTableView table={m.meta.table} />}
              {m.meta && (
                <div className="mt-3 text-[0.75rem] text-mute">
                  Audit event{" "}
                  {canAudit ? (
                    <Link href={`/audit?event_id=${m.meta.auditEventId}`} className="underline hover:text-amber">
                      {m.meta.auditEventId.slice(0, 8)}
                    </Link>
                  ) : (
                    m.meta.auditEventId.slice(0, 8)
                  )}
                </div>
              )}
            </div>
          </article>
        ))}

        {pending && (
          <div data-testid="pending" role="status" className="border border-rule bg-surface">
            <div className="border-b border-rule px-4 py-1.5">
              <span className="label">Assistant</span>
            </div>
            <div className="px-4 py-4">
              <p>Searching approved sources and drafting a cited answer…</p>
              <p className="mt-1 text-[0.8rem] text-mute">
                Answers are not streamed. Elapsed {elapsed}s.
              </p>
            </div>
          </div>
        )}
        <div ref={end} />
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { can, me } = useSession();
  const canAsk = can("answer");
  const canAudit = can("read_audit");

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [panel, setPanel] = useState<PanelState | null>(null);

  const refreshList = useCallback(async () => {
    if (!canAsk) return;
    try {
      setConversations(await api.conversations());
    } catch {
      /* list is a convenience; the thread still works */
    }
  }, [canAsk]);

  useEffect(() => {
    if (me) void refreshList();
  }, [me, refreshList]);

  useEffect(() => {
    if (!pending) return;
    setElapsed(0);
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [pending]);

  async function openConversation(id: string) {
    setActiveId(id);
    setPanel(null);
    try {
      const detail = await api.conversation(id);
      setMessages(
        detail.turns.map((t) => ({
          id: nextId(),
          role: t.role === "user" ? "user" : "assistant",
          content: t.content,
          citations: t.citations ?? [],
        })),
      );
    } catch {
      setMessages([
        { id: nextId(), role: "assistant", content: "This conversation could not be loaded.", citations: [], error: true },
      ]);
    }
  }

  function newConversation() {
    setActiveId(null);
    setMessages([]);
    setPanel(null);
    setInput("");
  }

  async function openCitation(c: Citation) {
    setPanel({ status: "loading", citation: c });
    try {
      const chunk = await api.chunk(c.document_ref, c.chunk_id);
      setPanel({ status: "ok", citation: c, chunk });
    } catch {
      setPanel({ status: "missing", citation: c });
    }
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending || !canAsk) return;
    setInput("");
    setMessages((m) => [...m, { id: nextId(), role: "user", content: question, citations: [] }]);
    setPending(true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ASK_TIMEOUT_MS);
    try {
      const res = await api.ask(question, activeId, controller.signal);
      setActiveId(res.conversation_id);
      setMessages((m) => [
        ...m,
        {
          id: nextId(),
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          meta: {
            found: res.found,
            degraded: res.degraded,
            refused: res.refused,
            table: res.result_table ?? null,
            report: res.report ?? null,
            auditEventId: res.audit_event_id,
          },
        },
      ]);
      void refreshList();
    } catch (err) {
      const calm =
        controller.signal.aborted || (err instanceof ApiError && err.status === 503);
      const content = calm
        ? NOTICE_TEXT
        : err instanceof ApiError && err.status === 403
          ? "Your role is not permitted to ask the assistant."
          : "The request could not be completed. Please try again.";
      setMessages((m) => [
        ...m,
        { id: nextId(), role: "assistant", content, citations: [], error: !calm, notice: calm },
      ]);
    } finally {
      clearTimeout(timer);
      setPending(false);
    }
  }

  return (
    <Shell>
      <div className="relative flex h-full">
        <aside
          className={`${historyOpen ? "flex" : "hidden"} absolute inset-y-0 left-0 z-30 w-[280px] max-w-[85%] shrink-0 flex-col border-r border-rule bg-surface md:static md:z-auto md:flex md:max-w-none`}
        >
          <div className="border-b border-rule p-3">
            <button
              type="button"
              onClick={newConversation}
              disabled={!canAsk}
              className="btn flex w-full items-center justify-center gap-2"
            >
              <IconPlus size={16} />
              New conversation
            </button>
          </div>
          <div className="label px-4 pb-2 pt-3">Conversations</div>
          <ul data-testid="conversation-list" className="min-h-0 flex-1 overflow-y-auto">
            {conversations.map((c) => {
              const active = c.id === activeId;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setHistoryOpen(false);
                      void openConversation(c.id);
                    }}
                    aria-current={active ? "true" : undefined}
                    className={`block w-full border-l-[3px] px-4 py-2.5 text-left text-[0.85rem] ${
                      active ? "border-amber bg-raised text-amber" : "border-transparent hover:bg-raised"
                    }`}
                  >
                    <span className="line-clamp-2">{c.title}</span>
                    <span className="mt-0.5 block text-[0.7rem] text-mute">
                      {c.updated_at.slice(0, 16).replace("T", " ")}
                    </span>
                  </button>
                </li>
              );
            })}
            {canAsk && conversations.length === 0 && (
              <li className="px-4 py-2 text-[0.85rem] text-mute">No conversations yet.</li>
            )}
          </ul>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-rule px-3 py-2 md:hidden">
            <button type="button" onClick={() => setHistoryOpen((o) => !o)} className="btn" aria-expanded={historyOpen}>
              {historyOpen ? "Hide conversations" : "Conversations"}
            </button>
          </div>
          <Thread
            messages={messages}
            pending={pending}
            elapsed={elapsed}
            activeChunkId={panel?.citation.chunk_id ?? null}
            onOpen={(c) => void openCitation(c)}
            onStarter={(q) => void send(q)}
            canAudit={canAudit}
            canAsk={canAsk}
          />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
            className="border-t border-rule bg-surface p-4"
          >
            <div className="mx-auto flex max-w-[860px] items-end gap-3">
              <label htmlFor="question" className="sr-only">
                Question
              </label>
              <textarea
                id="question"
                value={input}
                rows={2}
                disabled={!canAsk || pending}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(input);
                  }
                }}
                placeholder={canAsk ? "Ask a question. Enter to send, Shift+Enter for a new line." : "Assistant not available for this role"}
                className="field resize-none"
              />
              <button type="submit" disabled={!canAsk || pending || !input.trim()} className="btn-amber flex items-center gap-2">
                Send
                <IconArrow size={16} />
              </button>
            </div>
          </form>
        </section>

        {panel && <PassagePanel state={panel} onClose={() => setPanel(null)} />}
      </div>
    </Shell>
  );
}
