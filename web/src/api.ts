import type {
  AskResult, CaptureSummary, CustomerRow, OrderRow, CaptureView, Commitment, Committed, ConversionRow, DecliningRow,
  InactiveRow, ManagerSummary, OverdueRow, PendingRow, User, VisitDetail, VisitRow,
} from "./types";

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "ff.token";
const USER_KEY = "ff.user";

export class ApiFailure extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
  /** True when the failure means the device is offline or the server is unreachable. */
  get isNetwork() { return this.status === 0; }
}

export const session = {
  get token(): string | null { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  get user(): User | null {
    try { const raw = localStorage.getItem(USER_KEY); return raw ? (JSON.parse(raw) as User) : null; } catch { return null; }
  },
  save(token: string, user: User) {
    try { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch { /* private mode */ }
  },
  clear() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch { /* ignore */ } },
};

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

async function request<T>(path: string, init: RequestInit = {}, extraHeaders: Record<string, string> = {}): Promise<T> {
  const headers: Record<string, string> = { ...extraHeaders };
  const token = session.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiFailure(0, "NETWORK", "Can't reach the server. You may be offline.");
  }
  if (response.status === 401 && !path.startsWith("/v1/auth/")) onUnauthorized();
  if (!response.ok) {
    let code = "HTTP_ERROR", message = `Request failed (${response.status})`, details: unknown;
    try {
      const body = await response.json();
      if (body?.error) { code = body.error.code; message = body.error.message; details = body.error.details; }
    } catch { /* non-JSON error */ }
    throw new ApiFailure(response.status, code, message, details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);
export const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `k-${Date.now()}-${Math.random().toString(36).slice(2)}`);

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>("/v1/auth/login", { method: "POST", body: json({ username, password }) }),

  register: (body: { username: string; name: string; password: string; role: "rep" | "manager"; territoryId?: string; signupCode?: string }) =>
    request<{ token: string; user: User }>("/v1/auth/register", { method: "POST", body: json(body) }),

  signupOptions: () =>
    request<{ territories: { id: string; name: string }[]; managerSignup: boolean; signupOpen: boolean }>("/v1/auth/territories"),

  health: () => request<{ status: string; providers: string }>("/health"),

  createCapture(opts: { audio?: Blob; transcript?: string; language: string; key: string; capturedAt?: string }) {
    const form = new FormData();
    form.set("language", opts.language);
    if (opts.audio) form.set("audio", opts.audio, "visit.wav");
    if (opts.transcript) form.set("transcript", opts.transcript);
    if (opts.capturedAt) form.set("capturedAt", opts.capturedAt);
    return request<CaptureView>("/v1/captures", { method: "POST", body: form }, { "Idempotency-Key": opts.key });
  },
  listCaptures: (limit = 20) => request<{ captures: CaptureSummary[] }>(`/v1/captures?limit=${limit}`),
  getCapture: (id: string) => request<CaptureView>(`/v1/captures/${id}`),
  answer: (id: string, revision: number, answer: unknown) =>
    request<CaptureView>(`/v1/captures/${id}/answers`, { method: "POST", body: json({ revision, answer }) }),
  correct: (id: string, revision: number, text: string) =>
    request<CaptureView>(`/v1/captures/${id}/corrections`, { method: "POST", body: json({ revision, text }) }),
  correctAudio(id: string, revision: number, audio: Blob) {
    const form = new FormData();
    form.set("revision", String(revision));
    form.set("audio", audio, "correction.wav");
    return request<CaptureView>(`/v1/captures/${id}/corrections/audio`, { method: "POST", body: form });
  },
  confirm: (id: string, revision: number, key: string) =>
    request<Committed>(`/v1/captures/${id}/confirm`, { method: "POST", body: json({ revision, speakReply: true }) }, { "Idempotency-Key": key }),
  cancel: (id: string) => request<CaptureView>(`/v1/captures/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => request<CaptureView>(`/v1/captures/${id}/retry`, { method: "POST" }),

  async audioUrl(path: string): Promise<string> {
    const token = session.token;
    const response = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) throw new ApiFailure(response.status, "AUDIO", "Audio not available");
    return URL.createObjectURL(await response.blob());
  },

  visits: (limit = 30) => request<{ visits: VisitRow[] }>(`/v1/visits?limit=${limit}`),
  visit: (id: string) => request<VisitDetail>(`/v1/visits/${id}`),
  commitments: (status: "open" | "done" | "all" = "open") => request<{ commitments: Commitment[] }>(`/v1/commitments?status=${status}`),
  patchCommitment: (id: string, body: { status?: "open" | "done"; dueDate?: string }) =>
    request<Commitment>(`/v1/commitments/${id}`, { method: "PATCH", body: json(body) }),

  orders: (limit = 50) => request<{ orders: OrderRow[] }>(`/v1/orders?limit=${limit}`),
  customers: () => request<{ customers: CustomerRow[] }>("/v1/customers"),

  managerSummary: () => request<ManagerSummary>("/v1/manager/summary"),
  overdue: () => request<{ rows: OverdueRow[] }>("/v1/manager/overdue-payments"),
  inactive: (days = 30) => request<{ rows: InactiveRow[] }>(`/v1/manager/inactive-retailers?days=${days}`),
  pending: () => request<{ rows: PendingRow[] }>("/v1/manager/pending-commitments"),
  conversion: () => request<{ rows: ConversionRow[] }>("/v1/manager/conversion"),
  declining: () => request<{ rows: DecliningRow[] }>("/v1/manager/declining-products"),
  ask: (text: string) => request<AskResult>("/v1/manager/ask", { method: "POST", body: json({ text }) }),
};
