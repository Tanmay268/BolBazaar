import { useEffect, useState } from "react";
import { ApiFailure, api, session } from "../api";
import { CallScreen } from "../calls/CallScreen";
import { RecentCalls } from "../calls/RecentCalls";
import { niceDate, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { BottomNav, Header } from "../Shell";
import type { AskResult, CallSummary, ConversionRow, DecliningRow, InactiveRow, ManagerSummary, OverdueRow, PendingRow, User, VisitRow } from "../types";

interface Data {
  summary: ManagerSummary;
  overdue: OverdueRow[];
  inactive: InactiveRow[];
  pending: PendingRow[];
  conversion: ConversionRow[];
  declining: DecliningRow[];
  visits: VisitRow[];
  calls: CallSummary[];
}

const SUGGESTIONS = [
  "Which retailers have overdue payments?",
  "Which retailers haven't ordered in 30 days?",
  "Which reps have the most pending follow-ups?",
  "Which rep has the best order conversion?",
  "Which products are declining?",
];

function Ring({ pct, label }: { pct: number; label: string }) {
  const r = 26, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, pct));
  return (
    <svg viewBox="0 0 64 64" width="64" height="64" role="img" aria-label={`${label} ${v}%`}>
      <circle cx="32" cy="32" r={r} className="ring-bg" />
      <circle cx="32" cy="32" r={r} className="ring-fg" strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 32 32)" />
      <text x="32" y="36" textAnchor="middle" className="ring-t">{Math.round(v)}%</text>
    </svg>
  );
}

function Bar({ pct, tone }: { pct: number; tone?: "warn" | "ok" }) {
  return <span className="mbar"><i className={tone} style={{ width: `${Math.max(3, Math.min(100, pct))}%` }} /></span>;
}

function Panel({ title, icon, empty, count, children }: { title: string; icon: string; empty: string; count: number; children: React.ReactNode }) {
  return (
    <section className="panel rise">
      <h3><span className="lcard-ico"><Icon name={icon} size={16} /></span>{title}</h3>
      {count === 0 ? <p className="empty empty-sm">{empty}</p> : children}
    </section>
  );
}

function Skeleton() {
  return <div className="skel-list"><div className="skel skel-hero" /><div className="skel" /><div className="skel" /></div>;
}

type Tab = "overview" | "ask" | "calls" | "feed";

export function ManagerApp({ user, online, onSignOut }: { user: User; online: boolean; onSignOut: () => void }) {
  const { t } = useI18n();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [callTarget, setCallTarget] = useState<{ customerId?: string; callId?: string } | null>(null);

  async function load() {
    try {
      const [summary, overdue, inactive, pending, conversion, declining, visits, calls] = await Promise.all([
        api.managerSummary(), api.overdue(), api.inactive(30), api.pending(), api.conversion(), api.declining(), api.visits(12), api.listCalls(12),
      ]);
      setData({ summary, overdue: overdue.rows, inactive: inactive.rows, pending: pending.rows, conversion: conversion.rows, declining: declining.rows, visits: visits.visits.filter((v) => v.purpose !== "phone_call"), calls: calls.calls });
      setError(null);
    } catch (e) { setError(e instanceof ApiFailure ? e.message : "Couldn't load the dashboard."); }
  }

  useEffect(() => { void load(); const timer = setInterval(() => void load(), 30000); return () => clearInterval(timer); }, []);

  async function ask(text: string) {
    if (text.trim().length < 3) return;
    setAsking(true); setQuestion(text); setTab("ask");
    try { setAnswer(await api.ask(text)); setError(null); }
    catch (e) { setError(e instanceof ApiFailure ? e.message : "Couldn't answer that."); }
    finally { setAsking(false); }
  }

  const s = data?.summary;
  const maxOut = Math.max(1, ...(data?.overdue ?? []).map((r) => r.outstandingPaise));
  const maxOpen = Math.max(1, ...(data?.pending ?? []).map((r) => r.open));
  const pane = (id: Tab) => `pane ${tab === id ? "pane-on" : ""}`;

  return (
    <div className="frame frame-wide">
      <Header user={user} online={online} />
      <main className="scroll">
        {error && <div className="error rise">{error}</div>}
        {!data || !s ? <Skeleton /> : (
          <div className="mgr">
            <div className={pane("overview")}>
              <div className="greet rise"><small>{niceDate(s.date)}</small><h2>{t("hello")}, {user.name.split(" ")[0]}</h2></div>

              <section className="hero-card rise">
                <div className="hero-glow" aria-hidden />
                <small>Order value today</small>
                <strong className="hero-num">{rupees(s.orderValueTodayPaise)}</strong>
                <span className="hero-sub">{s.ordersToday} orders · {s.visitsToday} visits across your territories</span>
              </section>

              <div className="kpi-row">
                <div className="tile"><small>Outstanding</small><strong>{rupees(s.outstandingPaise)}</strong></div>
                <div className="tile"><small>Open follow-ups</small><strong>{s.openCommitments}</strong></div>
                <div className={`tile ${s.overdueCommitments ? "tile-warn" : ""}`}><small>Overdue</small><strong>{s.overdueCommitments}</strong></div>
                <div className={`tile ${s.openComplaints ? "tile-warn" : ""}`}><small>Complaints</small><strong>{s.openComplaints}</strong></div>
              </div>

              <div className="mgr-grid">
                <Panel title="Overdue payments" icon="rupee" empty="No payments outstanding." count={data.overdue.length}>
                  {data.overdue.slice(0, 6).map((r) => (
                    <div className="mrow" key={r.customerId}>
                      <span className="grow">{r.customer}{r.overdueFollowUps > 0 && <span className="tag tag-warn">{r.overdueFollowUps} late</span>}</span>
                      <Bar pct={(r.outstandingPaise / maxOut) * 100} tone="warn" /><b>{rupees(r.outstandingPaise)}</b>
                    </div>
                  ))}
                </Panel>

                <Panel title="Order conversion · 90 days" icon="trend" empty="No visits recorded yet." count={data.conversion.length}>
                  {data.conversion.map((r) => (
                    <div className="mrow" key={r.repId}>
                      <Ring pct={r.conversionPct} label={r.rep} />
                      <span className="grow"><b>{r.rep}</b><small>{r.visitsWithOrder} of {r.visits} visits ended in an order</small></span>
                    </div>
                  ))}
                </Panel>

                <Panel title="Pending follow-ups by rep" icon="bolt" empty="No open follow-ups." count={data.pending.length}>
                  {data.pending.map((r) => (
                    <div className="mrow" key={r.repId}>
                      <span className="grow">{r.rep}{r.overdue > 0 && <span className="tag tag-warn">{r.overdue} late</span>}</span>
                      <Bar pct={(r.open / maxOpen) * 100} /><b>{r.open}</b>
                    </div>
                  ))}
                </Panel>

                <Panel title="Declining products" icon="alert" empty="No product is declining." count={data.declining.length}>
                  {data.declining.slice(0, 6).map((r) => (
                    <div className="mrow" key={r.productId}>
                      <span className="grow">{r.product}<small>{r.priorQty} → {r.recentQty} units</small></span>
                      <Bar pct={r.declinePct} tone="warn" /><b>−{r.declinePct}%</b>
                    </div>
                  ))}
                </Panel>

                <Panel title="Quiet retailers · 30+ days" icon="clock" empty="Everyone ordered recently." count={data.inactive.length}>
                  {data.inactive.slice(0, 6).map((r) => (
                    <div className="mrow" key={r.customerId}>
                      <span className="grow">{r.customer}<small>{r.lastOrderDate ? `last order ${niceDate(r.lastOrderDate)}` : "never ordered"}</small></span>
                      {r.daysSinceOrder != null && <b>{r.daysSinceOrder}d</b>}
                    </div>
                  ))}
                </Panel>
              </div>
            </div>

            <div className={pane("ask")}>
              <section className="panel ask-panel rise">
                <h3><span className="lcard-ico"><Icon name="spark" size={16} /></span>{t("ask")}</h3>
                <form className="ask-form" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
                  <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Kin retailers ka payment overdue hai?" aria-label={t("ask")} />
                  <button className="btn btn-primary" disabled={asking || question.trim().length < 3} aria-label="Ask"><Icon name="send" size={18} /></button>
                </form>
                <div className="chips chips-scroll">{SUGGESTIONS.map((q) => <button key={q} className="chip" onClick={() => void ask(q)}>{q}</button>)}</div>
                {asking && <div className="working"><span className="spinner" />Checking the data…</div>}
                {answer && !asking && (
                  <div className="answer pop">
                    <p className="answer-text">{answer.answerText}</p>
                    {answer.rows.length > 0 && (
                      <div className="table-wrap"><table>
                        <thead><tr>{Object.keys(answer.rows[0]).filter((k) => !k.endsWith("Id")).map((k) => <th key={k}>{k.replace(/Paise$/, "").replace(/([A-Z])/g, " $1").toLowerCase()}</th>)}</tr></thead>
                        <tbody>{answer.rows.slice(0, 10).map((r, i) => (
                          <tr key={i}>{Object.entries(r).filter(([k]) => !k.endsWith("Id")).map(([k, v]) => <td key={k}>{k.endsWith("Paise") ? rupees(Number(v)) : String(v ?? "—")}</td>)}</tr>
                        ))}</tbody>
                      </table></div>
                    )}
                    <p className="note">Answered from a fixed query (<code>{answer.intent}</code>). The AI picks the question; the numbers come from SQL.</p>
                  </div>
                )}
              </section>
            </div>

            <div className={pane("calls")}>
              <Panel title={t("toCall")} icon="mic" empty="No retailer has an outstanding balance." count={data.overdue.filter((r) => r.outstandingPaise > 0).length}>
                {data.overdue.filter((r) => r.outstandingPaise > 0).slice(0, 8).map((r) => (
                  <div className="mrow" key={r.customerId}>
                    <span className="grow">{r.customer}<small>{rupees(r.outstandingPaise)} outstanding{r.overdueFollowUps ? ` · ${r.overdueFollowUps} overdue` : ""}</small></span>
                    <button className="btn btn-soft btn-sm" onClick={() => setCallTarget({ customerId: r.customerId })}><Icon name="mic" size={14} />{t("callNow")}</button>
                  </div>
                ))}
              </Panel>
              <section className="panel rise"><h3><span className="lcard-ico"><Icon name="list" size={16} /></span>{t("recentCalls")}</h3>
                <RecentCalls calls={data.calls} onOpen={(callId) => setCallTarget({ callId })} /></section>
            </div>

            <div className={pane("feed")}>
              <Panel title={t("feed")} icon="list" empty="No visits yet." count={data.visits.length}>
                {data.visits.map((v) => (
                  <div className="mrow" key={v.id}>
                    <span className="grow"><b>{v.customer}</b><small>{v.summary ?? v.purpose ?? "Visit"}</small></span>
                    <span className="right">{v.hasOrder && <b>{rupees(v.orderTotalPaise)}</b>}<small>{timeAgo(v.visitedAt)}</small></span>
                  </div>
                ))}
              </Panel>
              <button className="btn btn-ghost btn-wide signout" onClick={() => { session.clear(); onSignOut(); }}><Icon name="logout" size={18} />{t("signOut")}</button>
            </div>
          </div>
        )}
      </main>
      {callTarget && <CallScreen {...callTarget} onClose={(changed) => { setCallTarget(null); if (changed) void load(); }} />}
      <BottomNav active={tab} onSelect={(id) => setTab(id as Tab)} items={[
        { id: "overview", label: t("overview"), icon: "home" },
        { id: "ask", label: t("askTab"), icon: "spark" },
        { id: "calls", label: t("calls"), icon: "mic", badge: data?.calls.filter((c) => c.status === "NEEDS_REVIEW").length || undefined },
        { id: "feed", label: t("feed"), icon: "list" },
      ]} />
    </div>
  );
}
