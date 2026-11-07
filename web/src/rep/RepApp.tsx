import { useCallback, useEffect, useMemo, useState } from "react";
import { api, session } from "../api";
import { Storefront } from "../brand";
import { ACTION_LABEL, niceDate, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { LangToggle, useI18n } from "../i18n";
import { flushQueue, queue } from "../queue";
import { AppBar, BottomNav } from "../Shell";
import type { CaptureSummary, Commitment, OrderRow, User, VisitDetail, VisitRow } from "../types";
import { LogVisit } from "./LogVisit";

type Screen = "today" | "visits" | "orders" | "more" | "followups" | "log";

const isToday = (iso: string) => new Date(iso).toDateString() === new Date().toDateString();
const two = (n: number) => String(n).padStart(2, "0");

function Skeleton({ rows = 3 }: { rows?: number }) {
  return <div className="skel-list">{Array.from({ length: rows }, (_, i) => <div key={i} className="skel" />)}</div>;
}

function PromiseRow({ c, onChange }: { c: Commitment; onChange: () => void }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <div className={`list-row ${c.overdue ? "list-row-red" : ""} ${done ? "row-done" : ""}`}>
      <button className="check-btn" aria-label={t("done")} onClick={() => { setDone(true); api.patchCommitment(c.id, { status: "done" }).then(onChange).catch(() => setDone(false)); }}>
        {done ? <Icon name="check" size={16} stroke={3} /> : null}
      </button>
      <div className="grow">
        <b>{c.customer}</b>
        <span className="sub">{c.description}</span>
        <span className="sub"><span className="chip">{ACTION_LABEL[c.actionType] ?? c.actionType}</span> {niceDate(c.dueDate)}{c.overdue && <span className="chip-red">{t("overdue")}</span>}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------- Today
function Today({ user, go, refreshKey }: { user: User; go: (s: Screen) => void; refreshKey: number }) {
  const { t } = useI18n();
  const [visits, setVisits] = useState<VisitRow[] | null>(null);
  const [promises, setPromises] = useState<Commitment[] | null>(null);
  const [waiting, setWaiting] = useState<CaptureSummary[]>([]);

  const load = useCallback(() => {
    api.visits(50).then((r) => setVisits(r.visits)).catch(() => setVisits([]));
    api.commitments("open").then((r) => setPromises(r.commitments)).catch(() => setPromises([]));
    api.listCaptures(20).then((r) => setWaiting(r.captures.filter((c) => ["NEEDS_CLARIFICATION", "READY_FOR_REVIEW", "FAILED"].includes(c.state)))).catch(() => undefined);
  }, []);
  useEffect(load, [load, refreshKey]);

  const todays = useMemo(() => (visits ?? []).filter((v) => isToday(v.visitedAt)), [visits]);
  const booked = todays.reduce((n, v) => n + v.orderTotalPaise, 0);
  const overdue = (promises ?? []).filter((c) => c.overdue).length;
  const today = new Date().toLocaleDateString("en-CA");
  const due = (promises ?? []).filter((c) => c.overdue || c.dueDate <= today).slice(0, 3);

  return (
    <div className="home">
      <section className="home-hero">
        <Storefront className="home-art" />
        <h1 className="home-greet">{t("hello")},<br />{user.name.split(" ")[0]}</h1>
        <p className="home-date">{new Date().toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })}</p>
      </section>

      <button className="kpi-red" onClick={() => go("visits")}>
        <small>{t("todaysVisits")}</small>
        <b>{two(todays.length)}</b>
        <span className="kpi-sub">{rupees(booked)} {t("booked")}</span>
        <Icon name="arrow" size={30} stroke={2.2} />
      </button>

      <div className="kpi-pair">
        <button className="kpi-tile" onClick={() => go("followups")}><b>{two(promises?.length ?? 0)}</b><small>{t("followUps")}</small></button>
        <button className="kpi-tile" onClick={() => go("followups")}><b>{two(overdue)}</b><small>{t("overdue")}</small></button>
      </div>

      <button className="btn btn-ink btn-wide btn-lg" onClick={() => go("log")}><Icon name="mic" size={22} />{t("logVisit")}</button>

      {waiting.length > 0 && (
        <button className="list-row list-row-red" onClick={() => go("log")}>
          <Icon name="clock" size={20} /><span className="grow"><b>{t("waiting")}</b><span className="sub">{waiting.length} draft{waiting.length > 1 ? "s" : ""} to review</span></span><Icon name="right" size={18} />
        </button>
      )}

      <section>
        <div className="section-title">{t("promisesDue")}</div>
        {!promises ? <Skeleton rows={2} /> : due.length === 0 ? <p className="empty">{t("nothingDue")}</p> : <div className="stack-sm">{due.map((c) => <PromiseRow key={c.id} c={c} onChange={load} />)}</div>}
      </section>
    </div>
  );
}

// ------------------------------------------------------------------------- Visits
function Visits({ refreshKey, onLog }: { refreshKey: number; onLog: () => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<VisitRow[] | null>(null);
  const [open, setOpen] = useState<VisitDetail | null>(null);
  useEffect(() => { api.visits().then((r) => setRows(r.visits)).catch(() => setRows([])); }, [refreshKey]);

  if (open) {
    return (
      <div className="stack">
        <button className="link" onClick={() => setOpen(null)}><Icon name="back" size={16} />{t("tabVisits")}</button>
        <div><h1 className="title">{open.customer.name}</h1><p className="meta">{timeAgo(open.visitedAt)}</p></div>
        {open.summary && <p className="summary">{open.summary}</p>}
        <div className="rv">
          {open.order && (
            <div className="rv-row"><div className="rv-head"><span className="rv-ico"><Icon name="box" size={22} stroke={1.6} /></span><span className="rv-main"><small>Order</small><b>{rupees(open.order.totalPaise)}</b></span></div>
              <div className="rv-items">{open.order.items.map((i, k) => <div className="rv-item" key={k}><span className="rv-item-name">{i.product}</span><span className="rv-item-qty">× {i.quantity}</span><span className="rv-item-amt">{rupees(i.lineTotalPaise)}</span></div>)}</div></div>
          )}
          {open.collections.map((c) => (
            <div className="rv-row" key={c.id}><div className="rv-head"><span className="rv-ico"><Icon name="rupee" size={22} stroke={1.6} /></span><span className="rv-main"><small>Payment {c.kind}</small><b>{rupees(c.amountPaise)}{c.dueDate ? ` · ${niceDate(c.dueDate)}` : ""}</b></span></div></div>
          ))}
          {open.commitments.map((c) => (
            <div className="rv-row" key={c.id}><div className="rv-head"><span className="rv-ico"><Icon name="flag" size={22} stroke={1.6} /></span><span className="rv-main"><small>{ACTION_LABEL[c.actionType] ?? c.actionType}</small><b>{c.description}</b><small>{niceDate(c.dueDate)} · {c.status}</small></span></div></div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="stack">
      <div className="page-head"><h1 className="title">{t("tabVisits")}</h1><button className="btn btn-red btn-sm" onClick={onLog}><Icon name="mic" size={16} />{t("logVisit")}</button></div>
      {!rows ? <Skeleton rows={4} /> : !rows.length ? <p className="empty">{t("noVisits")}</p> : (
        <div className="stack-sm">
          {rows.map((v) => (
            <button key={v.id} className="list-row" onClick={() => api.visit(v.id).then(setOpen)}>
              <div className="grow"><b>{v.customer}</b><span className="sub clamp">{v.summary ?? v.purpose ?? "Visit"}</span></div>
              <div className="right">{v.hasOrder && <b>{rupees(v.orderTotalPaise)}</b>}<small>{timeAgo(v.visitedAt)}</small></div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------- Orders
function Orders({ refreshKey }: { refreshKey: number }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { api.orders().then((r) => setRows(r.orders)).catch(() => setRows([])); }, [refreshKey]);
  return (
    <div className="stack">
      <h1 className="title">{t("tabOrders")}</h1>
      {!rows ? <Skeleton rows={4} /> : !rows.length ? <p className="empty">{t("noOrders")}</p> : (
        <div className="stack-sm">
          {rows.map((o) => (
            <div key={o.id} className="list-card">
              <button className="list-row list-row-bare" onClick={() => setOpen(open === o.id ? null : o.id)} aria-expanded={open === o.id}>
                <div className="grow"><b>{o.customer}</b><span className="sub">{o.items.length} item{o.items.length === 1 ? "" : "s"}{o.deliveryDate ? ` · deliver ${niceDate(o.deliveryDate)}` : ""}</span></div>
                <div className="right"><b>{rupees(o.totalPaise)}</b><small>{timeAgo(o.createdAt)}</small></div>
              </button>
              {open === o.id && <div className="rv-items rv-items-flush">{o.items.map((i, k) => <div className="rv-item" key={k}><span className="rv-item-name">{i.product}</span><span className="rv-item-qty">× {i.quantity}</span><span className="rv-item-amt">{rupees(i.lineTotalPaise)}</span></div>)}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------- Follow-ups
function FollowUps({ refreshKey, onBack }: { refreshKey: number; onBack: () => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Commitment[] | null>(null);
  const load = useCallback(() => { api.commitments("open").then((r) => setRows(r.commitments)).catch(() => setRows([])); }, []);
  useEffect(load, [load, refreshKey]);
  return (
    <div className="stack">
      <button className="link" onClick={onBack}><Icon name="back" size={16} />{t("tabMore")}</button>
      <h1 className="title">{t("followUps")}</h1>
      {!rows ? <Skeleton rows={4} /> : !rows.length ? <p className="empty">{t("nothingDue")}</p> : <div className="stack-sm">{rows.map((c) => <PromiseRow key={c.id} c={c} onChange={load} />)}</div>}
    </div>
  );
}

// ------------------------------------------------------------------------- More
function More({ user, online, pending, go, onSignOut }: { user: User; online: boolean; pending: number; go: (s: Screen) => void; onSignOut: () => void }) {
  const { t } = useI18n();
  return (
    <div className="stack">
      <h1 className="title">{t("tabMore")}</h1>
      <div className="list-row list-row-bare"><span className="avatar">{user.name.slice(0, 1)}</span><div className="grow"><b>{user.name}</b><span className="sub">{user.organization} · {user.role}</span></div></div>
      <button className="list-row" onClick={() => go("followups")}><Icon name="flag" size={20} /><span className="grow"><b>{t("followUps")}</b></span><Icon name="right" size={18} /></button>
      <div className="list-row list-row-bare"><span className="grow">{t("language")}</span><LangToggle /></div>
      <div className="list-row list-row-bare"><span className="grow">Connection</span><span className={online ? "chip" : "chip-red"}>{online ? "Online" : t("offline")}</span></div>
      <div className="list-row list-row-bare"><span className="grow">Upload queue</span><span className="chip">{pending} {pending === 1 ? "item" : "items"}</span></div>
      <button className="btn btn-outline btn-wide" onClick={onSignOut}><Icon name="logout" size={18} />{t("signOut")}</button>
    </div>
  );
}

// ------------------------------------------------------------------------- shell
export function RepApp({ user, online, onSignOut }: { user: User; online: boolean; onSignOut: () => void }) {
  const { t } = useI18n();
  const [screen, setScreen] = useState<Screen>("today");
  const [pending, setPending] = useState(0);
  const [language, setLanguage] = useState("hinglish");
  const [uploaded, setUploaded] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshCount = useCallback(() => { void queue.count().then(setPending); }, []);
  useEffect(() => { refreshCount(); }, [refreshCount]);
  useEffect(() => {
    if (!online) return;
    void flushQueue().then(({ sent, left }) => { setPending(left); if (sent) { setUploaded((n) => n + sent); setRefreshKey((k) => k + 1); } });
  }, [online]);

  const signOut = () => { session.clear(); onSignOut(); };
  const nav = screen === "followups" ? "more" : screen;

  if (screen === "log") {
    return (
      <div className="phone">
        <LogVisit online={online} language={language} setLanguage={setLanguage} onQueueChange={refreshCount}
          onSaved={() => setRefreshKey((k) => k + 1)} onExit={() => { setScreen("today"); setRefreshKey((k) => k + 1); }} />
      </div>
    );
  }

  return (
    <div className="phone">
      <AppBar online={online} onMenu={() => setScreen("more")} />
      {pending > 0 && <div className="banner">{pending} {t("queued")}{online ? "…" : ""}</div>}
      {uploaded > 0 && online && pending === 0 && <div className="banner banner-ok" onClick={() => setUploaded(0)}>{uploaded} offline recording{uploaded > 1 ? "s" : ""} uploaded — see “{t("waiting")}”.</div>}
      <main className="page" key={screen}>
        {screen === "today" && <Today user={user} go={setScreen} refreshKey={refreshKey} />}
        {screen === "visits" && <Visits refreshKey={refreshKey} onLog={() => setScreen("log")} />}
        {screen === "orders" && <Orders refreshKey={refreshKey} />}
        {screen === "followups" && <FollowUps refreshKey={refreshKey} onBack={() => setScreen("more")} />}
        {screen === "more" && <More user={user} online={online} pending={pending} go={setScreen} onSignOut={signOut} />}
      </main>
      <BottomNav active={nav} onSelect={(id) => setScreen(id as Screen)} items={[
        { id: "today", label: t("tabToday"), icon: "home" },
        { id: "visits", label: t("tabVisits"), icon: "calendar" },
        { id: "orders", label: t("tabOrders"), icon: "box" },
        { id: "more", label: t("tabMore"), icon: "more", badge: pending || undefined },
      ]} />
    </div>
  );
}
