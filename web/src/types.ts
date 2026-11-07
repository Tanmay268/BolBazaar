export type Role = "rep" | "manager" | "admin";

export interface User {
  id: string;
  name: string;
  role: Role;
  territoryId: string | null;
  organization: string;
  defaultLanguage: string;
}

export type CaptureState =
  | "RECORDED" | "TRANSCRIBING" | "EXTRACTING" | "NEEDS_CLARIFICATION"
  | "READY_FOR_REVIEW" | "COMMITTED" | "FAILED" | "CANCELLED";

export interface Option { value: string; label: string }

export interface Clarification {
  code: string;
  fieldPath: string;
  answerPath: string;
  answerType: "choice" | "number" | "date";
  options: Option[];
  question: string;
}

export interface DraftItem {
  spokenName: string;
  quantity: number | null;
  unit: string | null;
  productId: string | null;
  productName: string | null;
  matchStatus: string;
  unitPricePaise: number | null;
  confidence: number;
  evidence: string | null;
  /** Set when the rep chose "add as a new item": created in the catalogue when the visit is confirmed. */
  newProduct?: { name: string; baseUnit: string | null; pricePaise: number | null };
}

export interface BugReportRow {
  id: string; category: string; title: string; description: string; status: string;
  context: Record<string, unknown>; adminNote: string | null; createdAt: string; updatedAt: string;
  reporter?: string; role?: string;
}

export interface ProductDraftRow {
  name: string; baseUnit: string | null; priceRupees: number | null; unitsPerPack: number | null;
  aliases: string[]; evidence: string; issues: string[]; duplicateOf: string | null; include: boolean;
}

export interface ProductRow {
  id: string; name: string; baseUnit: string; unitsPerPack: number | null;
  pricePaise: number; active: boolean; aliases: string[];
}

export interface Draft {
  customer: { spokenName: string | null; customerId: string | null; name: string | null; matchStatus: string; confidence: number };
  visit: { purpose: string | null; summary: string | null };
  order: { items: DraftItem[]; deliveryText: string | null; deliveryDate: string | null };
  collections: { kind: "promised" | "received"; amountPaise: number | null; dueText: string | null; dueDate: string | null; evidence: string | null }[];
  complaints: { category: string; description: string; productSpokenName: string | null; evidence: string | null }[];
  competitorNotes: { competitor: string; note: string }[];
  commitments: { actionType: string; description: string; dueText: string | null; dueDate: string | null; priority: string; evidence: string | null }[];
  totalPaise: number;
}

export interface Reply { status: string; text: string; url: string | null }

export interface CaptureView {
  id: string;
  state: CaptureState;
  revision: number;
  language: string;
  source: "audio" | "text";
  transcript: string | null;
  draft: Draft | null;
  openIssues: string[];
  clarification: Clarification | null;
  error: { stage: string; category: string } | null;
  visitId: string | null;
  reply: Reply | null;
  createdAt: string;
  patch?: { path: string; old: unknown; new: unknown }[];
  unsupported?: string[];
  utterance?: string;
}

export interface CaptureSummary { id: string; state: CaptureState; language: string; revision: number; createdAt: string; visitId: string | null }

export interface Committed {
  captureId: string;
  visitId: string;
  orderId: string | null;
  orderTotalPaise: number;
  commitmentIds: string[];
  customer: { id: string; name: string };
  confirmationText: string;
  language: string;
  reply: Reply | null;
}

export interface VisitRow {
  id: string; customerId: string; customer: string; visitedAt: string;
  purpose: string | null; summary: string | null; hasOrder: boolean; orderTotalPaise: number;
}

export interface VisitDetail {
  id: string;
  customer: { id: string; name: string };
  visitedAt: string;
  purpose: string | null;
  summary: string | null;
  order: { id: string; totalPaise: number; deliveryDate: string | null;
    items: { product: string; quantity: number; unit: string; unitPricePaise: number; lineTotalPaise: number }[] } | null;
  collections: { id: string; kind: string; amountPaise: number; dueDate: string | null }[];
  complaints: { id: string; category: string; description: string; status: string }[];
  commitments: Commitment[];
}

export interface Commitment {
  id: string; customerId: string; customer: string | null; visitId: string;
  actionType: string; description: string; dueDate: string; priority: string;
  status: "open" | "done"; overdue: boolean; sourcePhrase: string | null;
}

export interface ManagerSummary {
  date: string; visitsToday: number; ordersToday: number; orderValueTodayPaise: number;
  openCommitments: number; overdueCommitments: number; outstandingPaise: number; openComplaints: number;
  visits30d: number; visitsPrev30d: number;
}

export interface OverdueRow { customerId: string; customer: string; outstandingPaise: number; overdueFollowUps: number; oldestDueDate: string | null; nextDueDate: string | null }
export interface InactiveRow { customerId: string; customer: string; lastOrderDate: string | null; daysSinceOrder: number | null }
export interface PendingRow { repId: string; rep: string; open: number; overdue: number }
export interface ConversionRow { repId: string; rep: string; visits: number; visitsWithOrder: number; conversionPct: number; orderValuePaise: number }
export interface DecliningRow { productId: string; product: string; recentQty: number; priorQty: number; declinePct: number }

export interface AskResult {
  intent: string;
  parameters: Record<string, unknown>;
  rows: Record<string, unknown>[];
  answerText: string;
  supportedQuestions?: string[];
}


export interface OrderRow {
  id: string; status: string; totalPaise: number; deliveryDate: string | null; customer: string; createdAt: string;
  items: { productId: string; product: string; quantity: number; unit: string; unitPricePaise: number; lineTotalPaise: number }[];
}

export interface CustomerRow { id: string; name: string; territoryId: string; outstandingPaise: number; aliases: string[] }
