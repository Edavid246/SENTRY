import type { components } from "./api-types";

export type Schemas = components["schemas"];
export type QueryResponse = Schemas["AssistantQueryResponse"];
export type Citation = Schemas["CitationOut"];
export type ConversationSummary = Schemas["ConversationSummary"];
export type ConversationDetail = Schemas["ConversationDetail"];
export type ResultTable = Schemas["ResultTable"];
export type Finding = Schemas["FindingOut"];
export type RunResult = Schemas["RunResult"];
export type RecordDetail = Schemas["RecordDetail"];
export type ReportInfo = Schemas["ReportInfo"];
export type HomeSummary = Schemas["HomeSummary"];
export type HomeDivision = Schemas["HomeDivision"];
export type DivisionView = Schemas["DivisionView"];
export type DivisionSection = Schemas["Section"];
export type CaseView = Schemas["CaseView"];
export type DivisionReport = Schemas["DivisionReportOut"];

export type AccessToken = Schemas["AccessToken"];
export type Me = Schemas["Me"];
export type Chunk = Schemas["PassageOut"];
export type AuditEvent = Schemas["AuditEventOut"];
export type ChainTip = Schemas["ChainTip"];
export type VerifyReport = Schemas["VerifyReport"];
export type MapProperties = Schemas["MapProperties"];
export type MapKind = MapProperties["kind"];
export type MapFeature = Schemas["MapFeature"];
export type ConnectedMap = Schemas["ConnectedMap"];
export type ReplayBatch = Schemas["ReplayBatch"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const TOKEN_KEY = "dg.token";

export function readToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function storeToken(token: string | null): void {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* sessionStorage unavailable: the token lives in React state only */
  }
}

// Same-origin only: Next.js rewrites /api/* to the API (next.config.mjs).
async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const bearer = token ?? readToken();
  if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<AccessToken>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: (token?: string) => request<Me>("/me", {}, token),
  conversations: () => request<ConversationSummary[]>("/assistant/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/assistant/conversations/${id}`),
  ask: (question: string, conversationId: string | null, signal?: AbortSignal) =>
    request<QueryResponse>("/assistant/query", {
      method: "POST",
      body: JSON.stringify({ question, conversation_id: conversationId }),
      signal,
    }),
  chunk: (documentRef: string, chunkId: string) =>
    request<Chunk>(`/documents/${encodeURIComponent(documentRef)}/chunks/${chunkId}`),
  audit: (limit = 200, eventId?: string) =>
    request<AuditEvent[]>(
      `/audit?limit=${limit}${eventId ? `&event_id=${encodeURIComponent(eventId)}` : ""}`,
    ),
  runCorrelation: () => request<RunResult>("/correlation/run", { method: "POST" }),
  findings: () => request<Finding[]>("/correlation/findings"),
  finding: (id: string) => request<Finding>(`/correlation/findings/${encodeURIComponent(id)}`),
  record: (sourceRef: string) =>
    request<RecordDetail>(`/records/${encodeURIComponent(sourceRef)}`),
  home: () => request<HomeSummary>("/home/summary"),
  division: (key: string) => request<DivisionView>(`/divisions/${encodeURIComponent(key)}`),
  forensicCase: (caseRef: string) => request<CaseView>(`/cases/${encodeURIComponent(caseRef)}`),
  divisionReport: (key: string) =>
    request<DivisionReport>(`/reports/${encodeURIComponent(key)}`),
  serialTrace: (key: string, serial: string) =>
    request<DivisionSection>(
      `/divisions/${encodeURIComponent(key)}/trace?serial=${encodeURIComponent(serial)}`,
    ),
  connectedMap: (state?: string) =>
    request<ConnectedMap>(`/connected/map${state ? `?state=${encodeURIComponent(state)}` : ""}`),
  replay: (after: string | null, upto: string, state?: string) =>
    request<ReplayBatch>(
      `/connected/replay?upto=${encodeURIComponent(upto)}${after ? `&after=${encodeURIComponent(after)}` : ""}${state ? `&state=${encodeURIComponent(state)}` : ""}`,
    ),
  verify: () => request<VerifyReport>("/audit/verify"),
};

// The export is a file, not JSON: fetched with the same bearer token, then handed to the browser
// as a download. The server writes an audit event for every export.
export async function downloadReport(key: string, format: "pdf" | "docx"): Promise<void> {
  const bearer = readToken();
  const res = await fetch(`/api/v1/reports/${encodeURIComponent(key)}/export?format=${format}`, {
    headers: bearer ? { Authorization: `Bearer ${bearer}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1];
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name ?? `report.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}
