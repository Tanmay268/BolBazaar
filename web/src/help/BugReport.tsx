import { useEffect, useState } from "react";
import { ApiFailure, api, diagnostics } from "../api";
import { useI18n } from "../i18n";
import { timeAgo } from "../format";
import type { BugReportRow } from "../types";

const CATEGORIES: { value: string; en: string; hinglish: string }[] = [
  { value: "broken", en: "Something is broken or crashed", hinglish: "Kuch toot gaya ya crash hua" },
  { value: "wrong_result", en: "The app understood me wrongly", hinglish: "App ne galat samjha" },
  { value: "voice", en: "Microphone or voice problem", hinglish: "Mic ya awaaz ki dikkat" },
  { value: "suggestion", en: "Idea or suggestion", hinglish: "Sujhav" },
  { value: "other", en: "Something else", hinglish: "Kuch aur" },
];
const STATUS_TEXT: Record<string, string> = { open: "Received", in_progress: "Being looked at", resolved: "Resolved", wontfix: "Closed" };
export const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? "0.1.0";

/** Report a problem. Sends what the user wrote plus (optionally) non-sensitive technical details to help find the cause. */
export function BugReport({ online, page, onDone }: { online: boolean; page: string; onDone?: () => void }) {
  const { lang } = useI18n();
  const hi = lang === "hinglish";
  const [category, setCategory] = useState("broken");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [attach, setAttach] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [mine, setMine] = useState<BugReportRow[]>([]);
  const loadMine = () => { api.myBugReports().then((r) => setMine(r.reports)).catch(() => setMine([])); };
  useEffect(loadMine, []);

  const ready = title.trim().length >= 3 && description.trim().length >= 10 && online && !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const last = diagnostics.lastError;
      const r = await api.reportBug({
        category, title: title.trim(), description: description.trim(),
        context: attach ? { page, appVersion: APP_VERSION, platform: (navigator.platform || "web").slice(0, 100), language: lang,
          ...(last ? { lastError: { code: last.code, requestId: last.requestId, status: last.status, path: last.path } } : {}) } : undefined,
      });
      setSent(r.id); setTitle(""); setDescription(""); loadMine(); onDone?.();
    } catch (err) { setError(err instanceof ApiFailure ? err.message : "Couldn't send. Please try again."); }
    finally { setBusy(false); }
  }

  if (sent) {
    return (
      <div className="stack">
        <div className="block block-ok">
          <b>{hi ? "Shukriya! Aapki report mil gayi." : "Thank you! Your report was received."}</b>
          <p>{hi ? "Reference:" : "Reference:"} <code>{sent}</code></p>
          <button className="btn btn-outline btn-sm" onClick={() => setSent(null)}>{hi ? "Ek aur report karo" : "Report another"}</button>
        </div>
        <Mine rows={mine} />
      </div>
    );
  }
  return (
    <div className="stack">
      <p className="subtitle">{hi ? "Kya galat hua? Batao: kya kiya, kya hua, aur kya hona chahiye tha." : "What went wrong? Tell us what you did, what happened, and what you expected."}</p>
      <form className="bug-form" onSubmit={(e) => void submit(e)}>
        <label>{hi ? "Kis tarah ki dikkat?" : "What kind of problem?"}
          <select value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map((c) => <option key={c.value} value={c.value}>{hi ? c.hinglish : c.en}</option>)}</select></label>
        <label>{hi ? "Chhota title" : "Short title"}
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder={hi ? "Jaise: Confirm dabane par kuch nahi hota" : "e.g. Confirm button does nothing"} required /></label>
        <label>{hi ? "Detail mein batao" : "Describe it"}
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={5} maxLength={2000} required
            placeholder={hi ? "1. Maine ... kiya\n2. ... hua\n3. Mujhe ... chahiye tha" : "1. I did ...\n2. What happened ...\n3. What I expected ..."} />
          <small>{description.length}/2000 · {hi ? "kam se kam 10 akshar" : "at least 10 characters"}</small></label>
        <label className="bug-check"><input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} />
          <span>{hi ? "Technical details bhejo (screen, app version, aakhri error). Aapka password ya data nahi jata." : "Attach technical details (screen, app version, last error). Never your password or data."}</span></label>
        {error && <div className="error" role="alert">{error}</div>}
        {!online && <div className="notice">{hi ? "Bhejne ke liye internet chahiye." : "You need to be online to send this."}</div>}
        <button className="btn btn-red btn-wide" disabled={!ready}>{busy ? "…" : hi ? "Report bhejo" : "Send report"}</button>
      </form>
      <Mine rows={mine} />
    </div>
  );
}

function Mine({ rows }: { rows: BugReportRow[] }) {
  if (!rows.length) return null;
  return (
    <div className="bug-mine">
      <small className="eyebrow">Your reports</small>
      {rows.slice(0, 5).map((r) => (
        <div key={r.id} className="list-row list-row-bare">
          <span className="grow"><b>{r.title}</b><span className="sub">{timeAgo(r.createdAt)}{r.adminNote ? ` · ${r.adminNote}` : ""}</span></span>
          <span className={r.status === "resolved" ? "chip" : "chip-red"}>{STATUS_TEXT[r.status] ?? r.status}</span>
        </div>
      ))}
    </div>
  );
}
