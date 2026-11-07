import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiFailure, api, session } from "../api";
import { ACTION_LABEL, niceDate, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { LangToggle, useI18n } from "../i18n";
import { Sidebar, type NavItem } from "../Shell";
import { Wordmark } from "../brand";
import { HoldToTalk } from "../rep/HoldToTalk";
import { AdminBugs } from "../help/AdminBugs";
import { BugReport } from "../help/BugReport";
import { Manual } from "../help/Manual";
import { Tour, tourUnseen } from "../help/Tour";
import type {
  AskResult, ProductDraftRow, Commitment, ConversionRow, CustomerRow, DecliningRow, InactiveRow, ManagerSummary, OrderRow, OverdueRow, PendingRow, ProductRow, User, VisitRow,
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

type Page = "overview" | "ask" | "visits" | "orders" | "catalogue" | "promises" | "retailers" | "team" | "help" | "bug" | "bugs";

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
  const [tour, setTour] = useState(() => tourUnseen(user.id));
  const [lastPage, setLastPage] = useState<Page>("overview");
  useEffect(() => { if (!["help", "bug", "bugs"].includes(page)) setLastPage(page); }, [page]);
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
    { id: "catalogue", label: t("navCatalogue"), icon: "list" },
    { id: "promises", label: t("navPromises"), icon: "flag" },
    { id: "retailers", label: t("navRetailers"), icon: "store" },
    { id: "team", label: t("navTeam"), icon: "users" },
    ...(user.role === "admin" ? [{ id: "bugs", label: "Bug reports", icon: "alert" }] : []),
    { id: "help", label: "Help & manual", icon: "more" },
    { id: "bug", label: "Report a bug", icon: "alert" },
  ];

  const s = data?.summary;
  const today = s?.date ?? new Date().toLocaleDateString("en-CA");
  const heading = nav.find((n) => n.id === page)?.label ?? "";

  return (
    <div className="mgr">
      {tour && <Tour role={user.role} userId={user.id} onClose={() => setTour(false)} />}
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
          {page === "help" && <Manual role={user.role} onTour={() => setTour(true)} onReport={() => setPage("bug")} />}
          {page === "bug" && <BugReport online={online} page={`manager: ${lastPage}`} />}
          {page === "bugs" && user.role === "admin" && <AdminBugs />}
          {page === "help" || page === "bug" || page === "bugs" ? null : !data || !s ? <Skeleton /> : (
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
              {page === "catalogue" && <CataloguePage online={online} />}
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

const UNITS = ["kg", "packet", "bottle", "piece"];
const ISSUE_TEXT: Record<string, string> = {
  missing_price: "needs a price", missing_unit: "needs a unit", missing_name: "needs a name",
  duplicate: "already in catalogue", repeated: "listed twice",
};

interface ImportRow { include: boolean; name: string; unit: string; price: string; pack: string; aliases: string; issues: string[]; duplicateOf: string | null }
const toImport = (r: ProductDraftRow): ImportRow => ({
  include: r.include, name: r.name, unit: r.baseUnit ?? "", price: r.priceRupees != null ? String(r.priceRupees) : "",
  pack: r.unitsPerPack ? String(r.unitsPerPack) : "", aliases: r.aliases.join(", "), issues: r.issues, duplicateOf: r.duplicateOf,
});
const importReady = (r: ImportRow) => r.name.trim().length >= 2 && UNITS.includes(r.unit) && Number(r.price) > 0;

/** Say or type a whole product list; the assistant proposes rows; nothing is saved until the manager adds them. */
function ImportPanel({ online, onAdded }: { online: boolean; onAdded: () => void }) {
  const [text, setText] = useState("");
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const [heard, setHeard] = useState<string | null>(null);
  const [busy, setBusy] = useState<"read" | "add" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const fail = (e: unknown) => setError(e instanceof ApiFailure ? e.message : "That didn't work. Try again.");

  async function read(opts: { audio?: Blob; text?: string }) {
    setBusy("read"); setError(null); setDone(null);
    try {
      const r = await api.draftProducts(opts);
      setRows(r.items.map(toImport)); setHeard(r.transcript);
      if (r.items.length === 0) setError("I couldn't find any products in that. Say each item with its unit and price.");
      if (r.truncated) setError("That was a long list: only the first 100 items are shown. Add these, then do the rest.");
    } catch (e) { fail(e); } finally { setBusy(null); }
  }
  const set = (i: number, patch: Partial<ImportRow>) => setRows((rs) => rs && rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const chosen = rows?.filter((r) => r.include) ?? [];
  const canAdd = chosen.length > 0 && chosen.every(importReady) && !busy && online;

  async function add() {
    setBusy("add"); setError(null);
    try {
      const r = await api.bulkProducts(chosen.map((c) => ({ name: c.name.trim(), baseUnit: c.unit, priceRupees: Number(c.price),
        unitsPerPack: c.pack ? Number(c.pack) : undefined, aliases: c.aliases.split(",").map((a) => a.trim()).filter(Boolean) })));
      setDone(`Added ${r.created.length} item${r.created.length === 1 ? "" : "s"}.${r.skipped.length ? ` Skipped ${r.skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}.` : ""}`);
      setRows(null); setHeard(null); setText(""); onAdded();
    } catch (e) { fail(e); } finally { setBusy(null); }
  }

  return (
    <Panel title="Speak or type your whole list">
      <div className="cat-import">
        <p className="note">Read out your products with unit and price, for example <i>“chawal 60 rupaye kilo, atta 45 rupaye kilo, Parle-G 10 rupaye packet”</i>. You review everything before it is added.</p>
        <HoldToTalk label="Hold and speak your list" disabled={!!busy || !online} onError={setError} onRecorded={(b) => void read({ audio: b })} />
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={6000} aria-label="Product list"
          placeholder="or type / paste it here: chawal 60 rupaye kilo, atta 45 rupaye kilo ..." />
        <button className="btn btn-ink" disabled={!!busy || !online || text.trim().length < 3} onClick={() => void read({ text: text.trim() })}>
          {busy === "read" ? "Reading…" : "Read my list"}
        </button>
        {done && <div className="notice">{done}</div>}
        {error && <div className="error" role="alert">{error}</div>}
      </div>

      {rows && rows.length > 0 && (
        <>
          {heard && <p className="note cat-heard">I heard: “{heard}”</p>}
          <Table head={["Add", "Name", "Sold by", "Price (₹)", "Case of", "Check"]}>
            {rows.map((r, i) => (
              <tr key={i} className={r.include ? "" : "cat-retired"}>
                <td><input type="checkbox" checked={r.include} onChange={(e) => set(i, { include: e.target.checked })} aria-label={`Add ${r.name}`} /></td>
                <td><input value={r.name} onChange={(e) => set(i, { name: e.target.value })} aria-label="Name" /></td>
                <td><select value={r.unit} onChange={(e) => set(i, { unit: e.target.value })} aria-label="Unit"><option value="">?</option>{UNITS.map((u) => <option key={u}>{u}</option>)}</select></td>
                <td><input className="cat-num" type="number" min="0.01" step="0.01" value={r.price} onChange={(e) => set(i, { price: e.target.value })} aria-label="Price" /></td>
                <td><input className="cat-num" type="number" min="2" value={r.pack} onChange={(e) => set(i, { pack: e.target.value })} aria-label="Units per case" /></td>
                <td>{r.include && !importReady(r) ? <span className="chip-red">needs unit &amp; price</span>
                  : r.issues.filter((x) => x !== "missing_unit" && x !== "missing_price").map((x) => <span key={x} className="chip-red">{ISSUE_TEXT[x] ?? x}{x === "duplicate" && r.duplicateOf ? `: ${r.duplicateOf}` : ""}</span>)}</td>
              </tr>
            ))}
          </Table>
          <div className="cat-import-actions">
            <button className="btn btn-red" disabled={!canAdd} onClick={() => void add()}>{busy === "add" ? "Adding…" : `Add ${chosen.length} item${chosen.length === 1 ? "" : "s"} to catalogue`}</button>
            <button className="btn btn-outline" disabled={!!busy} onClick={() => { setRows(null); setHeard(null); }}>Discard</button>
          </div>
        </>
      )}
    </Panel>
  );
}

/** Manager's catalogue: add items, set prices, change names/spoken names, retire items. Reps can also add items by voice. */
function CataloguePage({ online }: { online: boolean }) {
  const [rows, setRows] = useState<ProductRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<string | null>(null);
  const blank = { name: "", unit: "kg", price: "", pack: "", aliases: "" };
  const [form, setForm] = useState(blank);
  const [draft, setDraft] = useState(blank);
  const load = useCallback(() => { api.products(true).then((r) => setRows(r.products)).catch((e) => { setRows([]); setError(e instanceof ApiFailure ? e.message : "Couldn't load the catalogue."); }); }, []);
  useEffect(load, [load]);
  const split = (text: string) => text.split(",").map((a) => a.trim()).filter(Boolean);
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await action(); load(); return true; }
    catch (e) { setError(e instanceof ApiFailure ? e.message : "That didn't work."); return false; }
    finally { setBusy(false); }
  }
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await run(() => api.createProduct({ name: form.name.trim(), baseUnit: form.unit, priceRupees: Number(form.price),
      unitsPerPack: form.pack ? Number(form.pack) : undefined, aliases: split(form.aliases) }));
    if (ok) setForm(blank);
  };
  const startEdit = (p: ProductRow) => { setEdit(p.id); setDraft({ name: p.name, unit: p.baseUnit, price: String(p.pricePaise / 100), pack: p.unitsPerPack ? String(p.unitsPerPack) : "", aliases: p.aliases.join(", ") }); };
  const save = async (p: ProductRow) => {
    const ok = await run(() => api.updateProduct(p.id, { name: draft.name.trim(), baseUnit: draft.unit, priceRupees: Number(draft.price),
      unitsPerPack: draft.pack ? Number(draft.pack) : null, aliases: split(draft.aliases) }));
    if (ok) setEdit(null);
  };
  return (
    <>
      <ImportPanel online={online} onAdded={load} />
      <Panel title="Add an item">
        <form className="cat-form" onSubmit={(e) => void add(e)}>
          <label>Name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Basmati Rice" required minLength={2} maxLength={120} /></label>
          <label>Sold by<select value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })}>{UNITS.map((u) => <option key={u}>{u}</option>)}</select></label>
          <label>Price (₹ per unit)<input type="number" min="0.01" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="60" required /></label>
          <label>Units per case <small>(optional)</small><input type="number" min="2" max="1000" value={form.pack} onChange={(e) => setForm({ ...form, pack: e.target.value })} placeholder="12" /></label>
          <label className="cat-wide">Other names reps say <small>(comma separated)</small><input value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} placeholder="chawal, rice" /></label>
          <button className="btn btn-red" disabled={busy || !online || !form.name.trim() || !form.price}>Add to catalogue</button>
        </form>
        {error && <div className="error cat-error" role="alert">{error}</div>}
      </Panel>

      <Panel title={`Catalogue${rows ? ` (${rows.filter((p) => p.active).length} active)` : ""}`}>
        {!rows ? <Skeleton /> : (
          <Table head={["Item", "Sold by", "Price (₹)", "Case of", "Spoken names", ""]} empty="No products yet. Add the first one above.">
            {rows.map((p) => edit === p.id ? (
              <tr key={p.id}>
                <td><input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} aria-label="Name" /></td>
                <td><select value={draft.unit} onChange={(e) => setDraft({ ...draft, unit: e.target.value })} aria-label="Unit">{UNITS.map((u) => <option key={u}>{u}</option>)}</select></td>
                <td><input className="cat-num" type="number" min="0.01" step="0.01" value={draft.price} onChange={(e) => setDraft({ ...draft, price: e.target.value })} aria-label="Price" /></td>
                <td><input className="cat-num" type="number" min="2" value={draft.pack} onChange={(e) => setDraft({ ...draft, pack: e.target.value })} aria-label="Units per case" /></td>
                <td><input value={draft.aliases} onChange={(e) => setDraft({ ...draft, aliases: e.target.value })} aria-label="Spoken names" /></td>
                <td className="cat-actions"><button className="btn btn-red btn-sm" disabled={busy} onClick={() => void save(p)}>Save</button> <button className="btn btn-outline btn-sm" onClick={() => setEdit(null)}>Cancel</button></td>
              </tr>
            ) : (
              <tr key={p.id} className={p.active ? "" : "cat-retired"}>
                <td>{p.name}{!p.active && <span className="chip"> retired</span>}</td><td>{p.baseUnit}</td><td className="num">{(p.pricePaise / 100).toLocaleString("en-IN")}</td>
                <td className="num">{p.unitsPerPack ?? "—"}</td><td className="wide">{p.aliases.join(", ") || "—"}</td>
                <td className="cat-actions">
                  <button className="btn btn-outline btn-sm" disabled={busy || !online} onClick={() => startEdit(p)}>Edit</button>{" "}
                  <button className="btn btn-outline btn-sm" disabled={busy || !online} onClick={() => void run(() => api.updateProduct(p.id, { active: !p.active }))}>{p.active ? "Retire" : "Restore"}</button>
                </td>
              </tr>
            ))}
          </Table>
        )}
        <p className="note cat-note">Changing a price affects new orders only; past orders keep the price they were saved with. Retired items disappear from new visits.</p>
      </Panel>
    </>
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
