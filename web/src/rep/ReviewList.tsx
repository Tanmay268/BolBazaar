import { useState } from "react";
import { ACTION_LABEL, niceDate, rupees } from "../format";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import type { CaptureView } from "../types";

function Row({ icon, label, title, right, ask, onClick, children }: {
  icon: string; label: string; title?: React.ReactNode; right?: React.ReactNode; ask?: boolean; onClick?: () => void; children?: React.ReactNode;
}) {
  const body = (
    <>
      <span className="rv-ico"><Icon name={icon} size={22} stroke={1.6} /></span>
      <span className="rv-main"><small>{label}</small>{title != null && <b>{title}</b>}</span>
      {right != null && <span className="rv-right">{right}</span>}
    </>
  );
  return (
    <div className={`rv-row ${ask ? "rv-ask" : ""}`}>
      {onClick ? <button type="button" className="rv-head" onClick={onClick}>{body}</button> : <div className="rv-head">{body}</div>}
      {children}
    </div>
  );
}

/** The extracted visit as a plain list of rows, in the same order the rep would say it. */
export function ReviewList({ view }: { view: CaptureView }) {
  const { t } = useI18n();
  const draft = view.draft;
  const [order, setOrder] = useState(true);
  const [follow, setFollow] = useState(false);
  const [said, setSaid] = useState(false);
  if (!draft) return null;
  const open = view.clarification?.fieldPath ?? "";
  const asking = (path: string) => !!open && (open === path || open.startsWith(`${path}.`));
  const items = draft.order.items;

  return (
    <div className="rv">
      {view.transcript && (
        <Row icon="quote" label={t("youSaid")} title={said ? undefined : <span className="rv-clip">{view.transcript}</span>}
          right={<Icon name={said ? "up" : "down"} size={18} />} onClick={() => setSaid((v) => !v)}>
          {said && <p className="rv-said">{view.transcript}</p>}
        </Row>
      )}

      <Row icon="store" label="Retailer" ask={asking("customer") || !draft.customer.customerId}
        title={draft.customer.name ?? draft.customer.spokenName ?? "Not identified"}
        right={draft.customer.customerId ? <Icon name="check" size={18} stroke={2.4} /> : <span className="chip-red">needs match</span>} />

      {items.length > 0 && (
        <>
          <Row icon="box" label="Order" title={<>{items.length} {items.length === 1 ? "item" : "items"} <span className="rv-count">· {rupees(draft.totalPaise)}</span></>}
            ask={asking("order")} right={<Icon name={order ? "up" : "down"} size={18} />} onClick={() => setOrder((v) => !v)}>
            {order && (
              <div className="rv-items">
                {items.map((item, i) => {
                  const line = item.quantity && item.unitPricePaise != null ? item.quantity * item.unitPricePaise : null;
                  return (
                    <div key={i} className={`rv-item ${asking(`order.items.${i}`) ? "rv-item-ask" : ""}`}>
                      <span className="rv-item-name">{item.productName ?? item.spokenName}{!item.productId && <em> · not in catalogue</em>}</span>
                      <span className="rv-item-qty">× {item.quantity ?? "?"}</span>
                      <span className="rv-item-amt">{rupees(line)}</span>
                    </div>
                  );
                })}
                <div className="rv-total"><span>Total</span><b>{rupees(draft.totalPaise)}</b></div>
              </div>
            )}
          </Row>
          <Row icon="calendar" ask={asking("order.deliveryDate")} label="Delivery"
            title={draft.order.deliveryDate ? niceDate(draft.order.deliveryDate) : draft.order.deliveryText ?? "No date mentioned"}
            right={draft.order.deliveryText && !draft.order.deliveryDate ? <span className="chip-red">date unclear</span> : undefined} />
        </>
      )}

      {draft.collections.map((c, i) => (
        <Row key={`c${i}`} icon="rupee" ask={asking(`collections.${i}`)} label={c.kind === "received" ? "Payment received" : "Payment promised"}
          title={`${rupees(c.amountPaise)}${c.dueDate ? ` · ${niceDate(c.dueDate)}` : c.dueText ? ` · ${c.dueText}` : ""}`} />
      ))}

      {draft.commitments.length > 0 && (
        <Row icon="flag" label={t("followUps")} title={String(draft.commitments.length)} ask={asking("commitments")}
          right={<Icon name={follow ? "up" : "down"} size={18} />} onClick={() => setFollow((v) => !v)}>
          {follow && (
            <div className="rv-items">
              {draft.commitments.map((c, i) => (
                <div key={i} className={`rv-item ${asking(`commitments.${i}`) ? "rv-item-ask" : ""}`}>
                  <span className="rv-item-name">{ACTION_LABEL[c.actionType] ?? c.actionType}: {c.description}</span>
                  <span className="rv-item-amt">{c.dueDate ? niceDate(c.dueDate) : <span className="chip-red">{c.dueText || "date?"}</span>}</span>
                </div>
              ))}
            </div>
          )}
        </Row>
      )}

      {draft.complaints.map((c, i) => <Row key={`x${i}`} icon="alert" label="Complaint" title={c.description} />)}
      {draft.competitorNotes.map((c, i) => <Row key={`k${i}`} icon="trend" label={c.competitor} title={c.note} />)}
    </div>
  );
}
