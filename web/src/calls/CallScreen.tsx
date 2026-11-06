import { useEffect, useRef, useState } from "react";
import { ApiFailure, api } from "../api";
import { niceDate, rupees } from "../format";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { HoldToTalk } from "../rep/HoldToTalk";
import type { CallApproval, CallOutcome, CallView } from "../types";

const VOICE_KEY = "ff.callvoice";
const QUICK = ["Kal tak de dunga", "Parso paanch hazaar denge", "Maal kharab tha, bill galat hai", "Abhi busy hoon, baad mein call karo"];
const LANG_FOR = (ui: string) => (ui === "en" ? "en-IN" : "hinglish");

const OUTCOME_LABEL: Record<string, string> = {
  promise_to_pay: "Promise to pay", claims_paid: "Says already paid", dispute: "Dispute raised",
  callback: "Call back requested", refused: "Declined to commit", wrong_person: "Wrong person", unresolved: "No outcome reached",
};

function OutcomeCard({ outcome, onApprove, onReject, busy }: { outcome: CallOutcome; onApprove: () => void; onReject: () => void; busy: boolean }) {
  const { t } = useI18n();
  const actionable = outcome.type === "promise_to_pay" || outcome.type === "callback" || outcome.type === "claims_paid" || outcome.type === "dispute";
  return (
    <div className="outcome pop">
      <small className="eyebrow">Proposed outcome — nothing is filed until you approve</small>
      <h3>{OUTCOME_LABEL[outcome.type] ?? outcome.type}</h3>
      <div className="tiles">
        {outcome.amountPaise != null && <div className="tile"><small>Amount</small><strong>{rupees(outcome.amountPaise)}</strong></div>}
        {outcome.dueDate && <div className="tile"><small>{outcome.type === "callback" ? "Call back on" : "By"}</small><strong className="tile-date">{niceDate(outcome.dueDate)}</strong></div>}
      </div>
      {outcome.amountAssumed && <p className="note">The retailer didn't state an amount, so the full balance was assumed. Check this before approving.</p>}
      {outcome.note && <p className="heard">“{outcome.note}”</p>}
      {!actionable && <p className="note">This outcome creates no follow-up. Approving just logs the call.</p>}
      <div className="actionbar actionbar-static">
        <button className="btn btn-quiet" disabled={busy} onClick={onReject}>{t("reject")}</button>
        <button className="btn btn-primary grow" disabled={busy} onClick={onApprove}><Icon name="check" size={18} />{t("approve")}</button>
      </div>
    </div>
  );
}

export function CallScreen({ customerId, callId, onClose }: { customerId?: string; callId?: string; onClose: (changed: boolean) => void }) {
  const { t, lang } = useI18n();
  const [call, setCall] = useState<CallView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [approval, setApproval] = useState<CallApproval | null>(null);
  const [voice, setVoice] = useState(() => { try { return localStorage.getItem(VOICE_KEY) !== "off"; } catch { return true; } });
  const changed = useRef(false);
  const played = useRef(new Set<number>());
  const audio = useRef<HTMLAudioElement | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  function fail(e: unknown) {
    if (e instanceof ApiFailure) setError(e.code === "NO_SPEECH" ? "I couldn't hear that. Try again." : e.code === "NOTHING_DUE" ? "This retailer has no outstanding balance." : e.message);
    else setError("Something went wrong.");
  }

  // Open an existing call, or start a new one exactly once (StrictMode runs effects twice in dev).
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (callId ? api.getCall(callId) : api.startCall(customerId!, LANG_FOR(lang)))
      .then((c) => { setCall(c); if (!callId) changed.current = true; if (callId) c.turns.forEach((x) => played.current.add(x.idx)); })
      .catch(fail);
    return () => { audio.current?.pause(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Speak each new agent line once.
  useEffect(() => {
    if (!call) return;
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    if (!voice) return;
    const next = call.turns.find((x) => x.role === "agent" && x.audioUrl && !played.current.has(x.idx));
    if (!next) return;
    played.current.add(next.idx);
    setSpeaking(true);
    api.audioUrl(next.audioUrl!).then((url) => {
      audio.current?.pause();
      const el = new Audio(url);
      audio.current = el;
      el.onended = el.onerror = () => setSpeaking(false);
      return el.play();
    }).catch(() => setSpeaking(false));
  }, [call, voice]);

  function toggleVoice() {
    setVoice((v) => { const n = !v; try { localStorage.setItem(VOICE_KEY, n ? "on" : "off"); } catch { /* ignore */ } if (!n) audio.current?.pause(); return n; });
  }

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function reply(text: string) {
    if (!call || !text.trim()) return;
    const next = await run(() => api.callTurnText(call.id, text.trim()));
    if (next) { setCall(next); setTyped(""); }
  }

  async function replyAudio(blob: Blob) {
    if (!call) return;
    const next = await run(() => api.callTurnAudio(call.id, blob));
    if (next) setCall(next);
  }

  async function hangUp() {
    if (!call) return onClose(changed.current);
    if (call.status === "ACTIVE") await run(() => api.cancelCall(call.id));
    onClose(true);
  }

  async function approve() {
    if (!call) return;
    const done = await run(() => api.approveCall(call.id));
    if (done) { setApproval(done); changed.current = true; }
  }

  async function reject() {
    if (!call) return;
    const next = await run(() => api.rejectCall(call.id));
    if (next) { changed.current = true; onClose(true); }
  }

  const active = call?.status === "ACTIVE";

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={t("callAgent")}>
      <div className="sheet-body">
        <header className="sheet-top">
          <button className="btn btn-soft btn-sm" onClick={() => void hangUp()} aria-label={t("hangUp")}><Icon name="x" size={16} />{active ? t("hangUp") : "Close"}</button>
          <div className="grow call-who">
            <b>{call?.customer.name ?? "Connecting…"}</b>
            <small>{call ? `${rupees(call.outstandingPaise)} outstanding` : ""}</small>
          </div>
          <button className={`icon-btn ${voice ? "on" : ""}`} onClick={toggleVoice} aria-pressed={voice} aria-label={t("voiceOn")} title={t("voiceOn")}><Icon name={voice ? "play" : "x"} size={16} /></button>
        </header>

        <div className="call-status">
          {active ? <span className={`live-dot ${speaking ? "speaking" : ""}`} /> : null}
          <small>{active ? (speaking ? "Agent speaking…" : "Live call · demo mode") : call?.status.replace("_", " ").toLowerCase()}</small>
        </div>

        <div className="call-thread">
          {!call && !error && <div className="working"><span className="spinner" />Connecting…</div>}
          {call?.turns.map((x) => (
            <div key={x.idx} className={`msg ${x.role === "agent" ? "msg-agent" : "msg-you"} rise`}>
              <small className="eyebrow">{x.role === "agent" ? "Agent" : "Retailer"}</small>
              <p>{x.text}</p>
            </div>
          ))}
          {busy && active && <div className="working"><span className="spinner" />…</div>}
          <div ref={end} />
        </div>

        {error && <div className="error" role="alert">{error}</div>}

        {approval ? (
          <div className="outcome pop">
            <div className="success-badge"><svg viewBox="0 0 52 52" width="52" height="52"><circle cx="26" cy="26" r="24" className="s-circle" /><path d="m15 27 8 8 15-17" className="s-tick" /></svg></div>
            <h3>Filed</h3>
            <p className="note">
              {approval.commitmentIds.length} follow-up{approval.commitmentIds.length === 1 ? "" : "s"}
              {approval.collectionIds.length ? `, ${approval.collectionIds.length} promised payment` : ""}
              {approval.complaintIds.length ? `, ${approval.complaintIds.length} complaint` : ""} created.
            </p>
            <button className="btn btn-primary btn-wide" onClick={() => onClose(true)}>Done</button>
          </div>
        ) : call?.status === "NEEDS_REVIEW" && call.outcome ? (
          <OutcomeCard outcome={call.outcome} busy={busy} onApprove={() => void approve()} onReject={() => void reject()} />
        ) : call && !active ? (
          <p className="empty">This call is {call.status.toLowerCase()}.</p>
        ) : active ? (
          <div className="call-input">
            <p className="note center">{t("actAsRetailer")}</p>
            <div className="chips chips-scroll">{QUICK.map((q) => <button key={q} className="chip" disabled={busy} onClick={() => void reply(q)}>{q}</button>)}</div>
            <HoldToTalk variant="bar" label="Hold to reply by voice" disabled={busy} onRecorded={(b) => void replyAudio(b)} onError={setError} />
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); void reply(typed); }}>
              <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type the retailer's reply…" aria-label="Retailer's reply" />
              <button className="btn btn-soft" disabled={!typed.trim() || busy} aria-label="Send"><Icon name="send" size={16} /></button>
            </form>
          </div>
        ) : null}
      </div>
    </div>
  );
}
