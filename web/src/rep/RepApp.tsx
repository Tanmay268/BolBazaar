import { useCallback, useEffect, useMemo, useState } from "react";
import { api, session } from "../api";
import { CallScreen } from "../calls/CallScreen";
import { RecentCalls } from "../calls/RecentCalls";
import { ACTION_LABEL, niceDate, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { LangToggle, useI18n } from "../i18n";
import { flushQueue, queue } from "../queue";
import { BottomNav, Header } from "../Shell";
import type { CallSummary, CaptureSummary, Commitment, User, VisitDetail, VisitRow } from "../types";
import { VisitThread } from "./VisitThread";

type Tab = "today" | "visits" | "talk" | "promises" | "you";

const isToday = (iso: string) => new Date(iso).toDateString() === new Date().toDateString();

function Skeleton({ rows = 3 }: { rows?: number }) {
  return <div className="skel-list">{Array.from({ length: rows }, (_, i) => <div key={i} className="skel" />)}</div>;
}

// ------------------------------------------------------------------------- Today
function Today({ user, go, refreshKey }: { user: User; go: (t: Tab) => void; refreshKey: number }) {
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

  const todays = useMemo(() => (visits ?? []).filter((v) => isToday(v.visitedAt) && v.purpose !== "phone_call"), [visits]);
  const booked = todays.reduce((n, v) => n + v.orderTotalPaise, 0);
  const due = (promises ?? []).filter((c) => c.overdue || c.dueDate <= new Date().toLocaleDateString("en-CA")).slice(0, 4);
  const overdue = (promises ?? []).filter((c) => c.overdue).length;
  const hour = new Date().getHours();
  const part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="stack">
      <div className="greet rise">
        <small>{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</small>
        <h2>{t("hello")}, {user.name.split(" ")[0]} <span className="wave" aria-hidden>👋</span></h2>
        <p>{part}.</p>
      </div>

      <section className="hero-card rise" style={{ animationDelay: "60ms" }}>
        <div className="hero-glow" aria-hidden />
        <small>{t("booked")}</small>
        <strong className="hero-num">{rupees(booked)}</strong>
        <span className="hero-sub">{todays.length} {todays.length === 1 ? "visit" : "visits"} · {todays.filter((v) => v.hasOrder).length} orders</span>
        <button className="btn btn-light" onClick={() => go("talk")}><Icon name="mic" size={18} />{t("logVisit")}</button>
      </section>

      <div className="tiles tiles-3 rise" style={{ animationDelay: "120ms" }}>
        <div className="tile"><small>{t("visitsToday")}</small><strong>{todays.length}</strong></div>
        <div className="tile"><small>Open promises</small><strong>{promises?.length ?? "–"}</strong></div>
        <div className={`tile ${overdue ? "tile-warn" : ""}`}><small>{t("overdue")}</small><strong>{overdue}</strong></div>
      </div>

      {waiting.length > 0 && (
        <button className="banner-card rise" onClick={() => go("talk")} style={{ animationDelay: "160ms" }}>
          <span className="banner-ico"><Icon name="clock" size={20} /></span>
          <span className="grow"><b>{t("waiting")}</b><small>{waiting.length} draft{waiting.length > 1 ? "s" : ""} to review</small></span>
          <Icon name="chevron" size={18} />
        </button>
      )}

      <section className="rise" style={{ animationDelay: "200ms" }}>
        <div className="section-title">{t("promisesDue")}</div>
        {!promises ? <Skeleton rows={2} /> : due.length === 0 ? <p className="empty">{t("nothingDue")}</p> : (
          <div className="stack-sm">
            {due.map((c) => <PromiseRow key={c.id} c={c} onChange={load} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function PromiseRow({ c, onChange, onCall }: { c: Commitment; onChange: () => void; onCall?: (customerId: string) => void }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <div className={`row-card ${c.overdue ? "row-card-warn" : ""} ${done ? "row-done" : ""}`}>
      <button className="check-btn" aria-label={t("done")} onClick={() => { setDone(true); api.patchCommitment(c.id, { status: "done" }).then(onChange).catch(() => setDone(false)); }}>
        {done ? <Icon name="check" size={16} /> : null}
      </button>
      <div className="grow">
        <b>{c.customer}</b>
        <span className="line-sub">{c.description}</span>
        <span className="line-sub"><span className="pill">{ACTION_LABEL[c.actionType] ?? c.actionType}</span> {niceDate(c.dueDate)}{c.overdue && <span className="tag tag-warn">{t("overdue")}</span>}</span>
      </div>
      {onCall && c.actionType === "payment_followup" && !done &&
        <button className="btn btn-soft btn-sm" onClick={() => onCall(c.customerId)} aria-label={`${t("callAgent")}: ${c.customer}`}><Icon name="mic" size={14} />{t("callNow")}</button>}
    </div>
  );
}

// ------------------------------------------------------------------------- Visits
function Visits({ refreshKey }: { refreshKey: number }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<VisitRow[] | null>(null);
  const [open, setOpen] = useState<VisitDetail | null>(null);
  useEffect(() => { api.visits().then((r) => setRows(r.visits)).catch(() => setRows([])); }, [refreshKey]);

  if (open) {
    return (
      <div className="stack rise">
        <button className="link" onClick={() => setOpen(null)}>← {t("tabVisits")}</button>
        <div><h2>{open.customer.name}</h2><p className="meta">{timeAgo(open.visitedAt)}</p></div>
        {open.summary && <p className="summary">{open.summary}</p>}
        {open.order && (
          <section className="lcard lcard-col">
            <div className="lcard-head"><span className="lcard-ico"><Icon name="receipt" size={18} /></span><small className="eyebrow">Order · {rupees(open.order.totalPaise)}</small></div>
            {open.order.items.map((i, k) => (
              <div className="oline" key={k}><span className="qtychip">{i.quantity}<small>{i.unit}</small></span><span className="grow oline-name">{i.product}</span><span className="amt">{rupees(i.lineTotalPaise)}</span></div>
            ))}
          </section>
        )}
        {open.collections.map((c) => (
          <section className="lcard" key={c.id}><div className="lcard-ico lcard-ico-money"><Icon name="rupee" size={18} /></div>
            <div className="grow"><small className="eyebrow">Payment {c.kind}</small><strong className="lcard-title">{rupees(c.amountPaise)}</strong><span className="heard">{niceDate(c.dueDate)}</span></div></section>
        ))}
        {open.commitments.map((c) => (
          <section className="lcard" key={c.id}><div className="lcard-ico lcard-ico-promise"><Icon name="bolt" size={18} /></div>
            <div className="grow"><small className="eyebrow">{ACTION_LABEL[c.actionType] ?? c.actionType}</small><strong className="lcard-title">{c.description}</strong><span className="heard">{niceDate(c.dueDate)} · {c.status}</span></div></section>
        ))}
      </div>
    );
  }
  if (!rows) return <Skeleton rows={4} />;
  if (!rows.length) return <p className="empty">{t("noVisits")}</p>;
  return (
    <div className="stack-sm">
      {rows.map((v, i) => (
        <button key={v.id} className="row-card rise" style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }} onClick={() => api.visit(v.id).then(setOpen)}>
          <span className="lcard-ico"><Icon name="user" size={18} /></span>
          <div className="grow"><b>{v.customer}</b><span className="line-sub">{v.summary ?? v.purpose ?? "Visit"}</span></div>
          <div className="right">{v.hasOrder && <b>{rupees(v.orderTotalPaise)}</b>}<small>{timeAgo(v.visitedAt)}</small></div>
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------- Promises
function Promises({ refreshKey, onCall, onOpenCall }: { refreshKey: number; onCall: (customerId: string) => void; onOpenCall: (id: string) => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Commitment[] | null>(null);
  const [calls, setCalls] = useState<CallSummary[]>([]);
  const load = useCallback(() => {
    api.commitments("open").then((r) => setRows(r.commitments)).catch(() => setRows([]));
    api.listCalls(8).then((r) => setCalls(r.calls)).catch(() => undefined);
  }, []);
  useEffect(load, [load, refreshKey]);
  if (!rows) return <Skeleton rows={4} />;
  return (
    <div className="stack">
      {rows.length ? <div className="stack-sm">{rows.map((c) => <PromiseRow key={c.id} c={c} onChange={load} onCall={onCall} />)}</div> : <p className="empty">{t("nothingDue")}</p>}
      {calls.length > 0 && <section><div className="section-title">{t("recentCalls")}</div><RecentCalls calls={calls} onOpen={onOpenCall} /></section>}
    </div>
  );
}

// ------------------------------------------------------------------------- You
function You({ user, online, pending, onSignOut }: { user: User; online: boolean; pending: number; onSignOut: () => void }) {
  const { t } = useI18n();
  return (
    <div className="stack">
      <section className="lcard rise">
        <span className="avatar avatar-lg">{user.name.slice(0, 1)}</span>
        <div className="grow"><strong className="lcard-title">{user.name}</strong><span className="heard">{user.organization} · {user.role}</span></div>
      </section>
      <section className="lcard lcard-col rise" style={{ animationDelay: "60ms" }}>
        <div className="setting"><span>{t("language")}</span><LangToggle /></div>
        <div className="setting"><span>Connection</span><span className={`tag ${online ? "tag-ok" : "tag-warn"}`}>{online ? "Online" : t("offline")}</span></div>
        <div className="setting"><span>Upload queue</span><span className="tag">{pending} {pending === 1 ? "item" : "items"}</span></div>
      </section>
      <button className="btn btn-ghost btn-wide" onClick={onSignOut}><Icon name="logout" size={18} />{t("signOut")}</button>
    </div>
  );
}

// ------------------------------------------------------------------------- shell
export function RepApp({ user, online, onSignOut }: { user: User; online: boolean; onSignOut: () => void }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("today");
  const [pending, setPending] = useState(0);
  const [language, setLanguage] = useState("hinglish");
  const [uploaded, setUploaded] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [callTarget, setCallTarget] = useState<{ customerId?: string; callId?: string } | null>(null);

  const refreshCount = useCallback(() => { void queue.count().then(setPending); }, []);
  useEffect(() => { refreshCount(); }, [refreshCount]);

  useEffect(() => {
    if (!online) return;
    void flushQueue().then(({ sent, left }) => { setPending(left); if (sent) { setUploaded((n) => n + sent); setRefreshKey((k) => k + 1); } });
  }, [online]);

  const titles: Record<Tab, string> = { today: t("tabToday"), visits: t("tabVisits"), talk: t("tabTalk"), promises: t("tabPromises"), you: t("tabYou") };

  return (
    <div className="frame">
      <Header user={user} online={online} />
      {pending > 0 && <div className="banner">{pending} {t("queued")}{online ? "…" : ""}</div>}
      {uploaded > 0 && online && pending === 0 && <div className="banner banner-ok" onClick={() => setUploaded(0)}>{uploaded} offline recording{uploaded > 1 ? "s" : ""} uploaded — see “{t("waiting")}”.</div>}
      <main className="scroll" key={tab}>
        {tab !== "today" && tab !== "talk" && <h1 className="page-title rise">{titles[tab]}</h1>}
        {tab === "today" && <Today user={user} go={setTab} refreshKey={refreshKey} />}
        {tab === "visits" && <Visits refreshKey={refreshKey} />}
        {tab === "talk" && <VisitThread online={online} onQueueChange={refreshCount} onSaved={() => setRefreshKey((k) => k + 1)} language={language} setLanguage={setLanguage} />}
        {tab === "promises" && <Promises refreshKey={refreshKey} onCall={(customerId) => setCallTarget({ customerId })} onOpenCall={(callId) => setCallTarget({ callId })} />}
        {tab === "you" && <You user={user} online={online} pending={pending} onSignOut={() => { session.clear(); onSignOut(); }} />}
      </main>
      {callTarget && <CallScreen {...callTarget} onClose={(changed) => { setCallTarget(null); if (changed) setRefreshKey((k) => k + 1); }} />}
      <BottomNav
        active={tab}
        onSelect={(id) => setTab(id as Tab)}
        items={[
          { id: "today", label: t("tabToday"), icon: "home" },
          { id: "visits", label: t("tabVisits"), icon: "list" },
          { id: "promises", label: t("tabPromises"), icon: "bolt" },
          { id: "you", label: t("tabYou"), icon: "user", badge: pending || undefined },
        ]}
        center={{ id: "talk", label: t("tabTalk"), icon: "mic" }}
      />
    </div>
  );
}
