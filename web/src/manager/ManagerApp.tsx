import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiFailure, api, session } from "../api";
import { ACTION_LABEL, niceDate, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { LangToggle, useI18n } from "../i18n";
import { Sidebar, type NavItem } from "../Shell";
import { Wordmark } from "../brand";
import type {
  AskResult, Commitment, ConversionRow, CustomerRow, DecliningRow, InactiveRow, ManagerSummary, OrderRow, OverdueRow, PendingRow, User, VisitRow,
} from "../types";

interface Data {
  summary: ManagerSummary;
  overdue: OverdueRow[];
  inactive: InactiveRow[];
  pending: PendingRow[];
  conversion: ConversionRow[];
  declining: DecliningRow[];
  visits: VisitRow[];
}

type Page = "overview" | "ask" | "visits" | "orders" | "promises" | "retailers" | "team";

const SUGGESTIONS = [
  "Which retailers have overdue payments?",
  "Which retailers haven't ordered in 30 days?",
  "Which reps have the most pending follow-ups?",
  "Which rep has the best order conversion?",
  "Which products are declining?",
];

const dayMs = 86_400_000;
const dayDiff = (iso: string, today: string) => Math.round((new Date(`${iso}T00:00:00`).getTime() - new Date(`${today}T00:00:00`).getTime()) / dayMs);

function DueChip({ next, today }: { next: string | null; today: string }) {
  if (!next) return <span className="chip">No follow-up</span>;
  const d = dayDiff(next, today);
  if (d < 0) return <span className="chip-red">{-d} day{d === -1 ? "" : "s"} late</span>;
  if (d === 0) return <span className="chip-red chip-solid">Due today</span>;
  if (d === 1) return <span className="chip">Due tomorrow</span>;
  return <span className="chip">{niceDate(next)}</span>;
}

function Panel({ title, action, children, className = "" }: { title: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <section className={`mpanel ${className}`}><header><h2>{title}</h2></header>{children}{action && <footer>{action}</footer>}</section>;
}

function Skeleton() {
  return <div className="skel-list"><div className="skel skel-hero" /><div className="skel" /><div className="skel" /></div>;
}

/** Calendar-style activity grid: one cell per day, red intensity = number of visits. */
function ActivityGrid({ visits, today }: { visits: VisitRow[]; today: string }) {
  const days = useMemo(() => {
    const counts = new Map<string, number>();
    visits.forEach((v) => { const k = new Date(v.visitedAt).toLocaleDateString("en-CA"); counts.set(k, (counts.get(k) ?? 0) + 1); });
    const base = new Date(`${today}T00:00:00`);
    return Array.from({ length: 28 }, (_, i) => {
      const d = new Date(base.getTime() - (27 - i) * dayMs);
      const key = d.toLocaleDateString("en-CA");
      return { key, label: d.toLocaleDateString("en-IN", { day: "numeric", month: "short" }), n: counts.get(key) ?? 0 };
    });
  }, [visits, today]);
  const max = Math.max(1, ...days.map((d) => d.n));
  const level = (n: number) => (n === 0 ? 0 : Math.min(4, Math.ceil((n / max) * 4)));
  return (
    <>
      <div className="heat" role="img" aria-label="Visits per day, last 28 days">
        {days.map((d) => <i key={d.key} className={`heat-${level(d.n)}`} title={`${d.label}: ${d.n} visit${d.n === 1 ? "" : "s"}`} />)}
      </div>
      <div className="heat-legend"><small>Less</small>{[0, 1, 2, 3, 4].map((l) => <i key={l} className={`heat-${l}`} />)}<small>More</small></div>
    </>
  );
}

function Table({ head, children, empty }: { head: string[]; children: React.ReactNode; empty?: string }) {
  const rows = Array.isArray(children) ? children.length : children ? 1 : 0;
  if (!rows && empty) return <p className="empty empty-sm">{empty}</p>;
  return <div className="table-wrap"><table><thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;
}

export function ManagerApp({ user, online, onSignOut }: { user: User; online: boolean; onSignOut: () => void }) {
  const { t } = useI18n();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>("overview");
  const [menu, setMenu] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResult | null>(null);
  const [asking, setAsking] = useState(false);

  const load = useCallback(async () => {
    try {
      const [summary, overdue, inactive, pending, conversion, declining, visits] = await Promise.all([
        api.managerSummary(), api.overdue(), api.inactive(30), api.pending(), api.conversion(), api.declining(), api.visits(100),
      ]);
      setData({ summary, overdue: overdue.rows, inactive: inactive.rows, pending: pending.rows, conversion: conversion.rows, declining: declining.rows, visits: visits.visits });
      setError(null);
    } catch (e) { setError(e instanceof ApiFailure ? e.message : "Couldn't load the dashboard."); }
  }, []);

  useEffect(() => { void load(); const timer = setInterval(() => void load(), 30000); return () => clearInterval(timer); }, [load]);

  async function ask(text: string) {
    if (text.trim().length < 3) return;
    setAsking(true); setQuestion(text); setPage("ask");
    try { setAnswer(await api.ask(text)); setError(null); }
    catch (e) { setError(e instanceof ApiFailure ? e.message : "Couldn't answer that."); }
    finally { setAsking(false); }
  }

  const nav: NavItem[] = [
    { id: "overview", label: t("navOverview"), icon: "home" },
    { id: "ask", label: t("navAsk"), icon: "spark" },
    { id: "visits", label: t("tabVisits"), icon: "calendar" },
    { id: "orders", label: t("navOrders"), icon: "box" },
    { id: "promises", label: t("navPromises"), icon: "flag" },
    { id: "retailers", label: t("navRetailers"), icon: "store" },
    { id: "team", label: t("navTeam"), icon: "users" },
  ];

  const s = data?.summary;
  const today = s?.date ?? new Date().toLocaleDateString("en-CA");
  const heading = nav.find((n) => n.id === page)?.label ?? "";

  return (
    <div className="mgr">
      <Sidebar items={nav} active={page} onSelect={(id) => setPage(id as Page)} open={menu} onClose={() => setMenu(false)}
        footer={<>
          <div className="side-user"><span className="avatar avatar-light">{user.name.slice(0, 1)}</span><div><b>{user.name}</b><small>{user.role}</small></div></div>
          <LangToggle />
          <button className="side-item" onClick={() => { session.clear(); onSignOut(); }}><Icon name="logout" size={20} />{t("signOut")}</button>
        </>} />

      <div className="mgr-main">
        <header className="mgr-bar">
          <button className="appbar-btn mgr-menu" onClick={() => setMenu(true)} aria-label="Menu"><Icon name="menu" size={26} /></button>
          <span className="mgr-brand"><Wordmark /></span>
          {!online && <span className="chip-red"><Icon name="wifioff" size={12} />{t("offline")}</span>}
        </header>

        <main className="mgr-page">
          <div className="mgr-head">
            <h1>{page === "overview" ? <>{t("areaOps")} <span>/ {user.organization}</span></> : heading}</h1>
            <div className="mgr-chips">
              <span className="pick"><Icon name="calendar" size={18} />{new Date(`${today}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</span>
              <span className="pick">{user.organization}</span>
            </div>
          </div>
          {error && <div className="error">{error}</div>}
          {!data || !s ? <Skeleton /> : (
            <>
              {page === "overview" && (() => {
                const v30 = s.visits30d, prev = s.visitsPrev30d;
                const delta = prev > 0 ? Math.round(((v30 - prev) / prev) * 100) : null;
                const tv = data.conversion.reduce((n, r) => n + r.visits, 0);
                const to = data.conversion.reduce((n, r) => n + r.visitsWithOrder, 0);
                const conv = tv ? Math.round((to / tv) * 100) : 0;
                const teamRows = [...data.conversion].sort((a, b) => b.orderValuePaise - a.orderValuePaise).slice(0, 5);
                return (
                  <>
                    <div className="kpi-strip">
                      <button className="kpi-red kpi-big" onClick={() => setPage("orders")}>
                        <b>{rupees(s.orderValueTodayPaise)}</b><small>Order Value Today</small>
                        <span className="kpi-sub">{s.ordersToday} orders · {s.visitsToday} visits today</span>
                        <Icon name="upright" size={30} stroke={2.2} />
                      </button>
                      <div className="metric"><b>{v30}</b><small>Visits · 30 days</small>{delta !== null && <em className={delta >= 0 ? "up" : "down"}>{delta >= 0 ? "+" : ""}{delta}%</em>}</div>
                      <div className="metric"><b>{rupees(s.outstandingPaise)}</b><small>Outstanding</small></div>
                      <div className="metric"><b>{conv}%</b><small>Order conversion · 90 days</small></div>
                    </div>

                    <div className="mgr-grid">
                      <Panel title={`Overdue Payments (${data.overdue.length})`} action={<button className="link-arrow" onClick={() => setPage("retailers")}>View all retailers<Icon name="arrow" size={18} /></button>}>
                        <Table head={["Retailer", "Amount", "Status"]} empty="No payments outstanding.">
                          {data.overdue.slice(0, 5).map((r) => (
                            <tr key={r.customerId}><td>{r.customer}</td><td className="num">{rupees(r.outstandingPaise)}</td><td><DueChip next={r.nextDueDate} today={today} /></td></tr>
                          ))}
                        </Table>
                      </Panel>

                      <Panel title="Team Performance" action={<button className="link-arrow" onClick={() => setPage("team")}>View team<Icon name="arrow" size={18} /></button>}>
                        <Table head={["Executive", "Visits", "Orders (₹)", "Conversion"]} empty="No visits recorded yet.">
                          {teamRows.map((r) => (
                            <tr key={r.repId}><td>{r.rep}</td><td className="num">{r.visits}</td><td className="num">{rupees(r.orderValuePaise)}</td><td><span className="pill-ink">{Math.round(r.conversionPct)}%</span></td></tr>
                          ))}
                        </Table>
                      </Panel>

                      <Panel title="Visit Activity" className="mpanel-heat"><ActivityGrid visits={data.visits} today={today} /><small className="foot-note">Last 28 days · each square is one day</small></Panel>
                    </div>
                  </>
                );
              })()}

              {page === "ask" && (
                <div className="ask">
                  <p className="subtitle">{t("askSub")}</p>
                  <form className="ask-form" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
                    <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={t("askPlaceholder")} aria-label={t("askTitle")} />
                    <button className="ask-go" disabled={asking || question.trim().length < 3} aria-label="Ask"><Icon name="arrow" size={24} stroke={2.2} /></button>
                  </form>
                  <div className="chips chips-scroll">{SUGGESTIONS.map((q) => <button key={q} className="chip chip-btn" onClick={() => void ask(q)}>{q}</button>)}</div>
                  {asking && <div className="working"><span className="spinner" />Checking the data…</div>}
                  {answer && !asking && (
                    <div className="answer">
                      <p className="answer-text">{answer.answerText}</p>
                      {answer.rows.length > 0 && (
                        <div className="table-wrap"><table>
                          <thead><tr>{Object.keys(answer.rows[0]).filter((k) => !k.endsWith("Id")).map((k) => <th key={k}>{k.replace(/Paise$/, "").replace(/([A-Z])/g, " $1").toLowerCase()}</th>)}</tr></thead>
                          <tbody>{answer.rows.slice(0, 10).map((r, i) => (
                            <tr key={i}>{Object.entries(r).filter(([k]) => !k.endsWith("Id")).map(([k, v]) => <td key={k} className={k.endsWith("Paise") ? "num" : ""}>{k.endsWith("Paise") ? rupees(Number(v)) : String(v ?? "—")}</td>)}</tr>
                          ))}</tbody>
                        </table></div>
                      )}
                      <p className="note">Answered from a fixed query (<code>{answer.intent}</code>). The AI picks the question; the numbers come from SQL.</p>
                    </div>
                  )}
                </div>
              )}

              {page === "visits" && (
                <Panel title={`Visits (${data.visits.length})`}>
                  <Table head={["Retailer", "Summary", "Order", "When"]} empty="No visits yet.">
                    {data.visits.map((v) => <tr key={v.id}><td>{v.customer}</td><td className="wide">{v.summary ?? v.purpose ?? "Visit"}</td><td className="num">{v.hasOrder ? rupees(v.orderTotalPaise) : "—"}</td><td>{timeAgo(v.visitedAt)}</td></tr>)}
                  </Table>
                </Panel>
              )}
              {page === "orders" && <OrdersPage />}
              {page === "promises" && <PromisesPage today={today} />}
              {page === "retailers" && <RetailersPage overdue={data.overdue} today={today} />}
              {page === "team" && (
                <Panel title="Team Performance">
                  <Table head={["Executive", "Visits", "Orders", "Order value", "Conversion", "Open follow-ups", "Overdue"]} empty="No visits recorded yet.">
                    {data.conversion.map((r) => {
                      const p = data.pending.find((x) => x.repId === r.repId);
                      return <tr key={r.repId}><td>{r.rep}</td><td className="num">{r.visits}</td><td className="num">{r.visitsWithOrder}</td><td className="num">{rupees(r.orderValuePaise)}</td>
                        <td><span className="pill-ink">{Math.round(r.conversionPct)}%</span></td><td className="num">{p?.open ?? 0}</td><td className="num">{p?.overdue ? <span className="chip-red">{p.overdue}</span> : 0}</td></tr>;
                    })}
                  </Table>
                </Panel>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function OrdersPage() {
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  useEffect(() => { api.orders(100).then((r) => setRows(r.orders)).catch(() => setRows([])); }, []);
  return (
    <Panel title={`Orders${rows ? ` (${rows.length})` : ""}`}>
      {!rows ? <Skeleton /> : (
        <Table head={["Retailer", "Items", "Total", "Delivery", "Placed"]} empty="No orders yet.">
          {rows.map((o) => <tr key={o.id}><td>{o.customer}</td><td className="wide">{o.items.map((i) => `${i.product} × ${i.quantity}`).join(", ")}</td><td className="num">{rupees(o.totalPaise)}</td><td>{o.deliveryDate ? niceDate(o.deliveryDate) : "—"}</td><td>{timeAgo(o.createdAt)}</td></tr>)}
        </Table>
      )}
    </Panel>
  );
}

function PromisesPage({ today }: { today: string }) {
  const [rows, setRows] = useState<Commitment[] | null>(null);
  const load = useCallback(() => { api.commitments("open").then((r) => setRows(r.commitments)).catch(() => setRows([])); }, []);
  useEffect(load, [load]);
  return (
    <Panel title={`Promises${rows ? ` (${rows.length})` : ""}`}>
      {!rows ? <Skeleton /> : (
        <Table head={["Retailer", "Action", "Details", "Due", ""]} empty="No open promises.">
          {rows.map((c) => (
            <tr key={c.id}><td>{c.customer}</td><td>{ACTION_LABEL[c.actionType] ?? c.actionType}</td><td className="wide">{c.description}</td>
              <td><DueChip next={c.dueDate} today={today} /></td>
              <td><button className="btn btn-outline btn-sm" onClick={() => api.patchCommitment(c.id, { status: "done" }).then(load)}>Done</button></td></tr>
          ))}
        </Table>
      )}
    </Panel>
  );
}

function RetailersPage({ overdue, today }: { overdue: OverdueRow[]; today: string }) {
  const [rows, setRows] = useState<CustomerRow[] | null>(null);
  useEffect(() => { api.customers().then((r) => setRows([...r.customers].sort((a, b) => b.outstandingPaise - a.outstandingPaise))).catch(() => setRows([])); }, []);
  const due = new Map(overdue.map((o) => [o.customerId, o]));
  return (
    <Panel title={`Retailers${rows ? ` (${rows.length})` : ""}`}>
      {!rows ? <Skeleton /> : (
        <Table head={["Retailer", "Outstanding", "Payment follow-up"]} empty="No retailers.">
          {rows.map((c) => <tr key={c.id}><td>{c.name}</td><td className="num">{c.outstandingPaise ? rupees(c.outstandingPaise) : "—"}</td><td><DueChip next={due.get(c.id)?.nextDueDate ?? null} today={today} /></td></tr>)}
        </Table>
      )}
    </Panel>
  );
}
