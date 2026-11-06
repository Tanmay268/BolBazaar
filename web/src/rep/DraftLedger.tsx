import { Icon } from "../Icon";
import { ACTION_LABEL, niceDate, rupees } from "../format";
import type { CaptureView, Draft } from "../types";

function Confidence({ value }: { value: number }) {
  const level = value >= 0.85 ? "high" : value >= 0.6 ? "mid" : "low";
  return <span className={`conf conf-${level}`} title={`${Math.round(value * 100)}% sure`} aria-label={`${Math.round(value * 100)} percent sure`}><i /><i /><i /></span>;
}

/** The structured proposal for a visit. Read-only: changes go through answers, corrections and confirm. */
export function DraftLedger({ view }: { view: CaptureView }) {
  const draft: Draft | null = view.draft;
  if (!draft) return null;
  const open = view.clarification?.fieldPath ?? "";
  const asking = (path: string) => !!open && (open === path || open.startsWith(`${path}.`));
  let n = 0;
  const delay = () => ({ animationDelay: `${(n++) * 70}ms` });

  return (
    <div className="ledger">
      <section className={`lcard rise ${asking("customer") || !draft.customer.customerId ? "lcard-ask" : ""}`} style={delay()}>
        <div className="lcard-ico"><Icon name="user" size={18} /></div>
        <div className="grow">
          <small className="eyebrow">Retailer</small>
          <strong className={draft.customer.name ? "lcard-title" : "lcard-title muted"}>
            {draft.customer.name ?? draft.customer.spokenName ?? "Not identified"}
          </strong>
          {draft.customer.name && draft.customer.spokenName && draft.customer.name.toLowerCase() !== draft.customer.spokenName.toLowerCase() &&
            <span className="heard">heard “{draft.customer.spokenName}”</span>}
        </div>
        <Confidence value={draft.customer.confidence} />
      </section>

      {draft.order.items.length > 0 && (
        <section className="lcard lcard-col rise" style={delay()}>
          <div className="lcard-head"><span className="lcard-ico"><Icon name="receipt" size={18} /></span><small className="eyebrow">Order</small></div>
          {draft.order.items.map((item, i) => {
            const line = item.quantity && item.unitPricePaise != null ? item.quantity * item.unitPricePaise : null;
            return (
              <div key={i} className={`oline ${asking(`order.items.${i}`) ? "oline-ask" : ""}`}>
                <span className="qtychip">{item.quantity ?? "?"}<small>{item.unit ?? ""}</small></span>
                <div className="grow">
                  <span className="oline-name">{item.productName ?? item.spokenName}</span>
                  {!item.productId && <span className="heard">“{item.spokenName}” — not in catalogue yet</span>}
                </div>
                <Confidence value={item.confidence} />
                <span className="amt">{rupees(line)}</span>
              </div>
            );
          })}
          <div className="ototal"><span>Total</span><strong>{rupees(draft.totalPaise)}</strong></div>
          <div className="deliver">
            <Icon name="clock" size={14} />
            {draft.order.deliveryDate ? `Deliver ${niceDate(draft.order.deliveryDate)}` : draft.order.deliveryText ? `Deliver: ${draft.order.deliveryText}` : "No delivery date mentioned"}
            {draft.order.deliveryText && !draft.order.deliveryDate && <span className="tag tag-warn">date unclear</span>}
          </div>
        </section>
      )}

      {draft.collections.map((c, i) => (
        <section key={`c${i}`} className="lcard rise" style={delay()}>
          <div className="lcard-ico lcard-ico-money"><Icon name="rupee" size={18} /></div>
          <div className="grow">
            <small className="eyebrow">{c.kind === "received" ? "Payment received" : "Payment promised"}</small>
            <strong className="lcard-title">{rupees(c.amountPaise)}</strong>
            <span className="heard">{c.dueDate ? niceDate(c.dueDate) : c.dueText ?? ""}</span>
          </div>
          <span className={`pill ${c.kind === "received" ? "pill-ok" : "pill-info"}`}>{c.kind}</span>
        </section>
      ))}

      {draft.commitments.map((c, i) => (
        <section key={`m${i}`} className={`lcard rise ${asking(`commitments.${i}`) ? "lcard-ask" : ""}`} style={delay()}>
          <div className="lcard-ico lcard-ico-promise"><Icon name="bolt" size={18} /></div>
          <div className="grow">
            <small className="eyebrow">{ACTION_LABEL[c.actionType] ?? c.actionType}</small>
            <strong className="lcard-title">{c.description}</strong>
            <span className="heard">{c.dueDate ? niceDate(c.dueDate) : <span className="tag tag-warn">{c.dueText || "date needed"}</span>}</span>
          </div>
        </section>
      ))}

      {draft.complaints.map((c, i) => (
        <section key={`x${i}`} className="lcard rise" style={delay()}>
          <div className="lcard-ico lcard-ico-bad"><Icon name="alert" size={18} /></div>
          <div className="grow"><small className="eyebrow">Complaint</small><strong className="lcard-title">{c.description}</strong></div>
        </section>
      ))}

      {draft.competitorNotes.map((c, i) => (
        <section key={`k${i}`} className="lcard rise" style={delay()}>
          <div className="lcard-ico"><Icon name="trend" size={18} /></div>
          <div className="grow"><small className="eyebrow">{c.competitor}</small><strong className="lcard-title">{c.note}</strong></div>
        </section>
      ))}
    </div>
  );
}
