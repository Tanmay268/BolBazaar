import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFailure, api, newKey } from "../api";
import { LANGUAGES, SAMPLE_TRANSCRIPT, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { queue } from "../queue";
import type { CaptureSummary, CaptureView, Committed } from "../types";
import { HoldToTalk } from "./HoldToTalk";
import { ReviewList } from "./ReviewList";
import { VoiceOrb } from "./VoiceOrb";

const MANUAL_MINUTES = 4; // assumption: typing one visit into a CRM form; shown as an estimate only

interface Props {
  onExit: () => void;
  onSaved: () => void;
  onQueueChange: () => void;
  online: boolean;
  language: string;
  setLanguage: (l: string) => void;
}

export function LogVisit({ onExit, onSaved, onQueueChange, online, language, setLanguage }: Props) {
  const { t } = useI18n();
  const [view, setView] = useState<CaptureView | null>(null);
  const [committed, setCommitted] = useState<Committed | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<CaptureSummary[]>([]);
  const [typed, setTyped] = useState("");
  const [showType, setShowType] = useState(false);
  const [editing, setEditing] = useState(false);
  const [answerText, setAnswerText] = useState("");
  const confirmKey = useRef<string | null>(null);
  const lastAttempt = useRef<{ blob?: Blob; transcript?: string; key: string; at: string } | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const started = useRef(0);

  const loadWaiting = useCallback(async () => {
    try {
      const { captures } = await api.listCaptures(20);
      setWaiting(captures.filter((c) => ["NEEDS_CLARIFICATION", "READY_FOR_REVIEW", "FAILED"].includes(c.state)));
    } catch { /* offline */ }
  }, []);
  useEffect(() => { void loadWaiting(); }, [loadWaiting, online]);

  useEffect(() => {
    if (busy !== "capture") return;
    setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, 2)), 1500);
    return () => clearInterval(timer);
  }, [busy]);

  useEffect(() => () => player.current?.pause(), []);

  async function play(path: string) {
    try {
      const url = await api.audioUrl(path);
      player.current?.pause();
      const audio = new Audio(url);
      player.current = audio;
      await audio.play();
    } catch { /* playback is a convenience; the text is always shown */ }
  }

  function fail(e: unknown) {
    if (e instanceof ApiFailure) {
      if (e.code === "STALE_REVISION" && view) { void refresh(); setError("The draft changed — refreshed."); return; }
      setError(e.code === "NO_SPEECH" ? "I couldn't hear anything. Try again, closer to the phone." : e.message);
    } else setError("Something went wrong.");
  }

  async function refresh() {
    if (!view) return;
    try { setView(await api.getCapture(view.id)); } catch (e) { fail(e); }
  }

  async function submit(input: { blob?: Blob; transcript?: string }, reuse?: { key: string; at: string }) {
    const attempt = { ...input, key: reuse?.key ?? newKey(), at: reuse?.at ?? new Date().toISOString() };
    lastAttempt.current = attempt;
    setError(null); setNotice(null); setCommitted(null);
    if (input.blob && !navigator.onLine) return saveOffline(attempt);
    started.current = Date.now();
    setBusy("capture");
    try {
      const created = await api.createCapture({ audio: input.blob, transcript: input.transcript, language, key: attempt.key, capturedAt: attempt.at });
      confirmKey.current = null;
      setView(created); setEditing(false);
    } catch (e) {
      if (e instanceof ApiFailure && e.isNetwork && input.blob) await saveOffline(attempt);
      else fail(e);
    } finally { setBusy(null); }
  }

  async function saveOffline(a: { blob?: Blob; key: string; at: string }) {
    if (!a.blob) return;
    await queue.add({ key: a.key, blob: a.blob, language, capturedAt: a.at, createdAt: Date.now() });
    onQueueChange();
    setNotice("No connection. Saved on this device — it will be processed automatically when you're back online.");
  }

  async function run<T>(name: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(name); setError(null);
    try { return await fn(); } catch (e) { fail(e); } finally { setBusy(null); }
  }

  async function sendAnswer(value: unknown) {
    if (!view) return;
    const next = await run("answer", () => api.answer(view.id, view.revision, value));
    if (next) { setView(next); setAnswerText(""); }
  }

  async function sendCorrection(text: string) {
    if (!view || !text.trim()) return;
    const next = await run("correct", () => api.correct(view.id, view.revision, text.trim()));
    if (next) { setView(next); setTyped(""); announce(next); }
  }

  async function sendCorrectionAudio(blob: Blob) {
    if (!view) return;
    const next = await run("correct", () => api.correctAudio(view.id, view.revision, blob));
    if (next) { setView(next); announce(next); }
  }

  function announce(next: CaptureView) {
    const parts: string[] = [];
    if (next.utterance) parts.push(`You said “${next.utterance}”`);
    if (next.patch?.length) parts.push(next.patch.map((p) => `${p.path.split(".").slice(-1)[0]}: ${String(p.old ?? "—")} → ${String(p.new ?? "removed")}`).join(" · "));
    if (next.unsupported?.length) parts.push(`Couldn't apply: ${next.unsupported.join("; ")}`);
    else if (next.patch && next.patch.length === 0) parts.push("Nothing changed");
    setNotice(parts.join(" — "));
  }

  async function confirm() {
    if (!view) return;
    confirmKey.current ??= newKey();
    const done = await run("confirm", () => api.confirm(view.id, view.revision, confirmKey.current!));
    if (done) {
      setCommitted(done); setView(null); void loadWaiting(); onSaved();
      navigator.vibrate?.([20, 40, 20]);
      if (done.reply?.url) void play(done.reply.url);
    }
  }

  async function discard() {
    if (!view) return;
    await run("cancel", () => api.cancel(view.id));
    toRecord();
  }

  async function resume(id: string) {
    const next = await run("open", () => api.getCapture(id));
    if (next) { setView(next); confirmKey.current = null; setCommitted(null); setNotice(null); setEditing(false); }
  }

  function toRecord() { setView(null); setCommitted(null); setNotice(null); setError(null); setTyped(""); setEditing(false); void loadWaiting(); }

  const q = view?.clarification;
  const steps = [t("stepListen"), t("stepUnderstand"), t("stepMatch")];

  // ------------------------------------------------------------------ saved
  if (committed) {
    const saved = Math.max(1, MANUAL_MINUTES - Math.round((Date.now() - started.current) / 60000));
    return (
      <div className="saved">
        <div className="saved-top">
          <svg viewBox="0 0 64 64" width="120" height="120" aria-hidden><path d="M10 34l16 16L56 14" className="saved-tick" /></svg>
          <h1>{t("visitSaved").split(" ").map((w) => <span key={w}>{w}</span>)}</h1>
          <p>{committed.customer.name}</p>
        </div>
        <div className="saved-bottom">
          <div className="saved-stats">
            <div><b>{rupees(committed.orderTotalPaise)}</b><small>Order</small></div>
            <div><b>{committed.commitmentIds.length}</b><small>{t("followUps")}</small></div>
            <div><b>~{saved} min</b><small>{t("timeSaved")}</small></div>
          </div>
          <blockquote className="saved-quote">“{committed.confirmationText}”</blockquote>
          {committed.reply?.url && <button className="link" onClick={() => void play(committed.reply!.url!)}><Icon name="play" size={16} />{t("playReply")}</button>}
          {committed.reply?.status === "FAILED" && <p className="meta">Voice reply unavailable — the visit is saved.</p>}
          <button className="btn btn-ink btn-wide" onClick={toRecord}>{t("logAnother")}<Icon name="arrow" size={20} /></button>
          <button className="link center" onClick={onExit}>{t("backToToday")}</button>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------ review
  if (view) {
    const failed = view.state === "FAILED";
    return (
      <div className="screen">
        <header className="appbar"><button className="appbar-btn" onClick={toRecord} aria-label="Back"><Icon name="back" size={26} /></button></header>
        <div className="screen-body">
          <h1 className="title">{t("reviewVisit")}</h1>
          <p className="subtitle">{t("reviewSub")}</p>

          {failed ? (
            <div className="block block-red">
              <p>That didn't go through ({view.error?.stage ?? "service"} problem). Your recording is safe.</p>
              <button className="btn btn-red" disabled={!!busy} onClick={() => void run("retry", () => api.retry(view.id)).then((n) => n && setView(n))}>Try again</button>
            </div>
          ) : <ReviewList view={view} />}

          {q && (
            <div className="block block-ask">
              <div className="block-head"><small className="eyebrow">{t("checkOne")}</small>
                <button className="link" onClick={() => void play(`/v1/captures/${view.id}/question-audio`)}><Icon name="play" size={14} />{t("hearIt")}</button></div>
              <p className="ask-q">{q.question}</p>
              {q.answerType === "choice" ? (
                <div className="chips">{q.options.map((o) => <button key={o.value} className="chip" disabled={!!busy} onClick={() => void sendAnswer(o.value)}>{o.label}</button>)}</div>
              ) : (
                <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (answerText) void sendAnswer(answerText); }}>
                  <input type={q.answerType === "date" ? "date" : "number"} inputMode={q.answerType === "number" ? "numeric" : undefined}
                    value={answerText} onChange={(e) => setAnswerText(e.target.value)} placeholder={q.answerType === "date" ? "" : "Number"} />
                  <button className="btn btn-red" disabled={!answerText || !!busy}><Icon name="arrow" size={18} /></button>
                </form>
              )}
            </div>
          )}

          {editing && !failed && (
            <div className="block edit-panel">
              <HoldToTalk label={`${t("correct")} — ${t("correctHint")}`} disabled={!!busy || !online} onRecorded={(b) => void sendCorrectionAudio(b)} onError={setError} />
              <form className="inline-form" onSubmit={(e) => { e.preventDefault(); void sendCorrection(typed); }}>
                <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="or type: Parle-G 15 kar do" aria-label="Type a correction" />
                <button className="btn btn-ink" disabled={!typed.trim() || !!busy} aria-label="Apply correction"><Icon name="arrow" size={18} /></button>
              </form>
              <button className="link" onClick={() => void discard()} disabled={!!busy}>{t("discard")}</button>
            </div>
          )}

          {notice && <div className="notice">{notice}</div>}
          {error && <div className="error" role="alert">{error}</div>}
        </div>

        <footer className="actions">
          <button className="btn btn-outline" disabled={!!busy || failed} onClick={() => setEditing((v) => !v)} aria-pressed={editing}>{t("edit")}</button>
          <button className="btn btn-red grow" disabled={view.state !== "READY_FOR_REVIEW" || !!busy} onClick={() => void confirm()}>
            {busy === "confirm" ? <span className="spinner spinner-on" /> : <>{q ? t("answerFirst") : t("confirm")}<Icon name="arrow" size={20} /></>}
          </button>
        </footer>
      </div>
    );
  }

  // ------------------------------------------------------------------ record / processing
  return (
    <div className="screen">
      <header className="appbar"><button className="appbar-btn" onClick={onExit} aria-label="Back"><Icon name="back" size={26} /></button></header>
      <div className="screen-body">
        <h1 className="title">{t("logVisit")}</h1>
        <p className="subtitle">{t("logSub")}</p>

        <VoiceOrb working={busy === "capture"} disabled={!!busy} onRecorded={(b) => void submit({ blob: b })} onError={setError} />

        {busy === "capture" && (
          <ol className="steps" role="status" aria-live="polite">
            {steps.map((s, i) => <li key={s} className={i < stage ? "done" : i === stage ? "now" : ""}><span>{i < stage ? "✓" : i + 1}</span>{s}…</li>)}
          </ol>
        )}

        <div className="lang-pick" role="radiogroup" aria-label={t("speechLanguage")}>
          {LANGUAGES.map((l) => (
            <button key={l.code} role="radio" aria-checked={language === l.code} className={language === l.code ? "on" : ""} onClick={() => setLanguage(l.code)}>{l.label}</button>
          ))}
        </div>

        {notice && <div className="notice">{notice}</div>}
        {error && (
          <div className="error" role="alert"><span>{error}</span>
            {lastAttempt.current && <button className="btn btn-sm btn-outline" onClick={() => void submit(lastAttempt.current!, lastAttempt.current!)}>Retry</button>}</div>
        )}

        <div className="alt">
          <button className="link" onClick={() => setShowType((v) => !v)}><Icon name="keyboard" size={16} />{t("typeInstead")}</button>
          <button className="link" onClick={() => void submit({ transcript: SAMPLE_TRANSCRIPT })} disabled={!!busy}><Icon name="spark" size={16} />{t("sample")}</button>
        </div>
        {showType && (
          <form className="typebox" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) { void submit({ transcript: typed.trim() }); setTyped(""); } }}>
            <textarea rows={3} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Gupta Store ko 10 packet Parle-G diye, 2000 rupaye kal denge…" />
            <button className="btn btn-ink" disabled={!typed.trim() || !!busy}>Process<Icon name="arrow" size={18} /></button>
          </form>
        )}

        {waiting.length > 0 && (
          <section className="waiting">
            <div className="section-title">{t("waiting")}</div>
            {waiting.map((c) => (
              <button key={c.id} className="list-row" onClick={() => void resume(c.id)}>
                <span className={`dot ${c.state === "FAILED" ? "dot-red" : ""}`} />
                <span className="grow">{c.state === "FAILED" ? "Needs a retry" : c.state === "NEEDS_CLARIFICATION" ? "Has a question" : "Ready to confirm"}</span>
                <small>{timeAgo(c.createdAt)}</small><Icon name="right" size={18} />
              </button>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
