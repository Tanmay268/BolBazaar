import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFailure, api, newKey } from "../api";
import { LANGUAGES, SAMPLE_TRANSCRIPT, rupees, timeAgo } from "../format";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { queue } from "../queue";
import type { CaptureSummary, CaptureView, Committed } from "../types";
import { DraftLedger } from "./DraftLedger";
import { HoldToTalk } from "./HoldToTalk";

const MANUAL_MINUTES = 4; // assumption: typing one visit into a CRM form; shown as an estimate only

interface Props {
  onQueueChange: () => void;
  onSaved: () => void;
  online: boolean;
  language: string;
  setLanguage: (l: string) => void;
}

export function VisitThread({ onQueueChange, onSaved, online, language, setLanguage }: Props) {
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
      setView(created);
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

  async function cancel() {
    if (!view) return;
    await run("cancel", () => api.cancel(view.id));
    reset();
  }

  async function resume(id: string) {
    const next = await run("open", () => api.getCapture(id));
    if (next) { setView(next); confirmKey.current = null; setCommitted(null); setNotice(null); }
  }

  function reset() { setView(null); setCommitted(null); setNotice(null); setError(null); setTyped(""); void loadWaiting(); }

  const q = view?.clarification;
  const steps = [t("stepListen"), t("stepUnderstand"), t("stepMatch")];

  // ------------------------------------------------------------------ success
  if (committed) {
    const saved = Math.max(1, MANUAL_MINUTES - Math.round((Date.now() - started.current) / 60000));
    return (
      <div className="success pop">
        <div className="success-badge"><svg viewBox="0 0 52 52" width="64" height="64"><circle cx="26" cy="26" r="24" className="s-circle" /><path d="m15 27 8 8 15-17" className="s-tick" /></svg></div>
        <h2>{t("visitSaved")}</h2>
        <p className="success-who">{committed.customer.name}</p>
        <div className="tiles">
          {committed.orderId && <div className="tile"><small>Order</small><strong>{rupees(committed.orderTotalPaise)}</strong></div>}
          <div className="tile"><small>Follow-ups</small><strong>{committed.commitmentIds.length}</strong></div>
          <div className="tile"><small>{t("saved")}</small><strong>~{saved} min</strong></div>
        </div>
        <blockquote className="reply">“{committed.confirmationText}”</blockquote>
        {committed.reply?.url &&
          <button className="btn btn-soft" onClick={() => void play(committed.reply!.url!)}><Icon name="play" size={16} />{t("playReply")}</button>}
        {committed.reply?.status === "FAILED" && <p className="meta">Voice reply unavailable — the visit is saved.</p>}
        <button className="btn btn-primary btn-wide" onClick={reset}>{t("nextVisit")}</button>
      </div>
    );
  }

  // ------------------------------------------------------------------ draft thread
  if (view) {
    const failed = view.state === "FAILED";
    return (
      <div className="thread">
        {view.transcript && (
          <div className="bubble-me rise">
            <small className="eyebrow">{view.source === "audio" ? "You said" : "You typed"}</small>
            <p>{view.transcript}</p>
          </div>
        )}
        {failed && (
          <div className="card card-bad rise">
            <p>That didn't go through ({view.error?.stage ?? "service"} problem). Your recording is safe.</p>
            <button className="btn btn-primary" disabled={!!busy} onClick={() => void run("retry", () => api.retry(view.id)).then((n) => n && setView(n))}>Try again</button>
          </div>
        )}
        {view.draft && <><div className="section-title"><Icon name="spark" size={14} />{t("understood")}</div><DraftLedger view={view} /></>}

        {q && (
          <div className="ask-card rise">
            <div className="ask-head"><small className="eyebrow">{t("checkOne")}</small>
              <button className="btn btn-sm btn-soft" onClick={() => void play(`/v1/captures/${view.id}/question-audio`)}><Icon name="play" size={14} />{t("hearIt")}</button>
            </div>
            <p className="ask-q">{q.question}</p>
            {q.answerType === "choice" && (
              <div className="chips">
                {q.options.map((o) => <button key={o.value} className="chip" disabled={!!busy} onClick={() => void sendAnswer(o.value)}>{o.label}</button>)}
              </div>
            )}
            {q.answerType !== "choice" && (
              <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (answerText) void sendAnswer(answerText); }}>
                <input type={q.answerType === "date" ? "date" : "number"} inputMode={q.answerType === "number" ? "numeric" : undefined}
                  value={answerText} onChange={(e) => setAnswerText(e.target.value)} placeholder={q.answerType === "date" ? "" : "Number"} />
                <button className="btn btn-primary" disabled={!answerText || !!busy}>OK</button>
              </form>
            )}
          </div>
        )}

        {notice && <div className="notice rise">{notice}</div>}
        {error && <div className="error rise" role="alert">{error}</div>}

        {!failed && (
          <div className="correct">
            <HoldToTalk variant="bar" label={`${t("correct")} — ${t("correctHint")}`} disabled={!!busy || !online} onRecorded={(b) => void sendCorrectionAudio(b)} onError={setError} />
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); void sendCorrection(typed); }}>
              <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="or type: Parle-G 15 kar do" aria-label="Type a correction" />
              <button className="btn btn-soft" disabled={!typed.trim() || !!busy} aria-label="Apply correction"><Icon name="send" size={16} /></button>
            </form>
          </div>
        )}

        <div className="actionbar">
          <button className="btn btn-quiet" disabled={!!busy} onClick={() => void cancel()}>{t("discard")}</button>
          <button className="btn btn-primary grow" disabled={view.state !== "READY_FOR_REVIEW" || !!busy} onClick={() => void confirm()}>
            {busy === "confirm" ? <span className="spinner spinner-on" /> : <Icon name="check" size={18} />}
            {q ? t("answerFirst") : t("confirm")}
          </button>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------ idle / processing
  return (
    <div className="talk">
      <div className="talk-head">
        <h2>{t("logVisit")}</h2>
        <p>{t("idleHint")}</p>
      </div>

      <HoldToTalk variant="orb" label={t("hold")} working={busy === "capture"} disabled={!!busy} onRecorded={(b) => void submit({ blob: b })} onError={setError} />

      {busy === "capture" && (
        <ol className="steps" role="status" aria-live="polite">
          {steps.map((s, i) => (
            <li key={s} className={i < stage ? "done" : i === stage ? "now" : ""}><span className="dot-step">{i < stage ? "✓" : i + 1}</span>{s}…</li>
          ))}
        </ol>
      )}

      <div className="seg seg-center" role="radiogroup" aria-label={t("speechLanguage")}>
        {LANGUAGES.map((l) => (
          <button key={l.code} role="radio" aria-checked={language === l.code} className={language === l.code ? "on" : ""} onClick={() => setLanguage(l.code)}>{l.label}</button>
        ))}
      </div>

      {notice && <div className="notice rise">{notice}</div>}
      {error && (
        <div className="error rise" role="alert">
          <span>{error}</span>
          {lastAttempt.current && <button className="btn btn-sm btn-soft" onClick={() => void submit(lastAttempt.current!, lastAttempt.current!)}>Retry</button>}
        </div>
      )}

      <div className="alt">
        <button className="link" onClick={() => setShowType((v) => !v)}><Icon name="keyboard" size={16} />{t("typeInstead")}</button>
        <button className="link" onClick={() => void submit({ transcript: SAMPLE_TRANSCRIPT })} disabled={!!busy}><Icon name="spark" size={16} />{t("sample")}</button>
      </div>
      {showType && (
        <form className="typebox rise" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) { void submit({ transcript: typed.trim() }); setTyped(""); } }}>
          <textarea rows={3} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Gupta Store ko 10 packet Parle-G diye, 2000 rupaye kal denge…" />
          <button className="btn btn-primary" disabled={!typed.trim() || !!busy}>Process</button>
        </form>
      )}

      {waiting.length > 0 && (
        <section className="waiting">
          <div className="section-title">{t("waiting")}</div>
          {waiting.map((c) => (
            <button key={c.id} className="row-card" onClick={() => void resume(c.id)}>
              <span className={`dot dot-${c.state === "FAILED" ? "bad" : "warn"}`} />
              <span className="grow">{c.state === "FAILED" ? "Needs a retry" : c.state === "NEEDS_CLARIFICATION" ? "Has a question" : "Ready to confirm"}</span>
              <small>{timeAgo(c.createdAt)}</small><Icon name="chevron" size={18} />
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
