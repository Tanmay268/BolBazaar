import { niceDate, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import type { CallSummary } from "../types";

const OUTCOME: Record<string, string> = {
  promise_to_pay: "Promise to pay", claims_paid: "Says already paid", dispute: "Dispute", callback: "Call back",
  refused: "Declined", wrong_person: "Wrong person", unresolved: "No outcome",
};
const STATUS: Record<string, { label: string; cls: string }> = {
  ACTIVE: { label: "In progress", cls: "tag-warn" },
  NEEDS_REVIEW: { label: "Needs review", cls: "tag-warn" },
  APPROVED: { label: "Filed", cls: "tag-ok" },
  REJECTED: { label: "Rejected", cls: "" },
  CANCELLED: { label: "Cancelled", cls: "" },
};

export function RecentCalls({ calls, onOpen }: { calls: CallSummary[]; onOpen: (id: string) => void }) {
  if (calls.length === 0) return <p className="empty empty-sm">No calls yet.</p>;
  return (
    <div className="stack-sm">
      {calls.map((c) => (
        <button key={c.id} className="row-card" onClick={() => onOpen(c.id)}>
          <span className="lcard-ico"><Icon name="mic" size={18} /></span>
          <div className="grow">
            <b>{c.customer}</b>
            <span className="line-sub">
              {c.outcomeType ? OUTCOME[c.outcomeType] ?? c.outcomeType : "Call"}
              {c.amountPaise != null && ` · ${rupees(c.amountPaise)}`}{c.dueDate && ` · ${niceDate(c.dueDate)}`}
            </span>
          </div>
          <div className="right"><span className={`tag ${STATUS[c.status]?.cls ?? ""}`}>{STATUS[c.status]?.label ?? c.status}</span><small>{timeAgo(c.createdAt)}</small></div>
        </button>
      ))}
    </div>
  );
}
