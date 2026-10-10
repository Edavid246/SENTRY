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
export type DashboardSummary =Schemas["DashboardSummary"];
export type ReportInfo = Schemas["ReportInfo"];
export type DashboardTile = Schemas["DashboardTile"];
export type DashboardItem = Schemas["DashboardItem"];
export type HomeSummary = Schemas["HomeSummary"];
export type HomeDivision = Schemas["HomeDivision"];
export type HomeAlert = Schemas["HomeAlert"];
export type DivisionView = Schemas["DivisionView"];
export type DivisionSection = Schemas["Section"];
export type ComplianceView = Schemas["ComplianceView"];
export type SectionRow = Schemas["SectionRow"];

// These endpoints return free-form dicts in OpenAPI, so their shapes are
// declared here (kept in step with backend/app/api/endpoints.py).
export interface Me {
  username: string;
  display_name: string;
  role: string;
  unit_path: string;
  unit_breadcrumb: { path: string; name: string }[];
  clearance_code: string | null;
  clearance_rank: number;
  compartments: string[];
  permissions: string[];
  data_scope: string;
}

export interface Chunk {
  chunk_id: string;
  document_id: string;
  document_ref: string;
  document_title: string;
  text: string;
  page: number | null;
  section: string | null;
  classification_code: string;
  compartments: string[];
}

export interface AuditEvent {
  seq: number;
  event_id: string;
  created_at: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ChainTip {
  seq: number;
  hash: string;
}

export interface VerifyReport {
  valid: boolean;
  checked_count: number;
  first_bad_event_id: string | null;
  checkpoint_ok: boolean | null;
  checkpoint_tip: ChainTip | null;
  ledger_ok: boolean | null;
  ledger_tip: ChainTip | null;
}

export type MapKind = "sensor" | "detection" | "mission";

export interface MapProperties {
  ref: string;
  kind: MapKind;
  label: string;
  classification: string;
  compartments: string[];
  unit_path: string;
  source_system: string;
  status?: string | null;
  observed_at?: string;
  object_type?: string;
  confidence?: number;
  site?: string;
  mission_date?: string;
  track_kind?: string;
  area?: string;
  reason?: string | null;
}

export interface MapFeature {
  type: "Feature";
  geometry:
    | { type: "Point"; coordinates: [number, number] }
    | { type: "LineString"; coordinates: [number, number][] };
  properties: MapProperties;
}

export interface ConnectedMap {
  type: "FeatureCollection";
  features: MapFeature[];
  generated_at: string;
}

export interface ReplayBatch {
  window_start: string;
  window_end: string;
  events: MapFeature[];
}

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
    request<{ access_token: string }>("/auth/login", {
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
  finding: (id: string) => request<Finding>(`/correlation/findings/${encodeURIComponent(id)}`),
  record: (sourceRef: string) =>
    request<RecordDetail>(`/records/${encodeURIComponent(sourceRef)}`),
  dashboard: () => request<DashboardSummary>("/dashboard/summary"),
  home: () => request<HomeSummary>("/home/summary"),
  division: (key: string) => request<DivisionView>(`/divisions/${encodeURIComponent(key)}`),
  compliance: () => request<ComplianceView>("/compliance"),
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
