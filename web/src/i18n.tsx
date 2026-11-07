import { createContext, useCallback, useContext, useMemo, useState } from "react";

const en = {
  hello: "Namaste",
  tabToday: "Today",
  tabVisits: "Visits",
  tabOrders: "Orders",
  tabMore: "More",
  logVisit: "Log a Visit",
  logSub: "Speak about the visit — retailer, order, payment, promises.",
  todaysVisits: "Today's visits",
  followUps: "Follow-ups",
  overdue: "Overdue",
  booked: "booked",
  timeSaved: "Time saved",
  tapToRecord: "Tap to record",
  orHold: "or press and hold",
  recording: "Recording",
  release: "release to send",
  typeInstead: "Can't talk? Type it",
  sample: "Try a sample visit",
  reviewVisit: "Review Visit",
  reviewSub: "Check and confirm the extracted details.",
  edit: "Edit",
  confirm: "Confirm",
  answerFirst: "Answer first",
  discard: "Discard draft",
  visitSaved: "Visit Saved",
  logAnother: "Log Another Visit",
  backToToday: "Back to Today",
  playReply: "Play spoken confirmation",
  stepListen: "Listening",
  stepUnderstand: "Understanding",
  stepMatch: "Matching",
  offline: "Offline",
  queued: "recording(s) waiting to upload",
  signOut: "Sign out",
  language: "App language",
  speechLanguage: "Speaking in",
  noVisits: "No visits yet. Log your first one.",
  noOrders: "No orders yet.",
  done: "Done",
  waiting: "Waiting for you",
  nothingDue: "All clear. Promises you record will show up here.",
  promisesDue: "Promises to keep",
  askTitle: "Ask",
  askSub: "Get insights from your team data.",
  askPlaceholder: "Which retailers have overdue payments?",
  checkOne: "One quick check",
  hearIt: "Hear it",
  correct: "Hold to correct",
  correctHint: "e.g. “make Parle-G 15”",
  youSaid: "You said",
  areaOps: "Area Operations",
  navOverview: "Overview",
  navAsk: "Ask",
  navOrders: "Orders",
  navPromises: "Promises",
  navRetailers: "Retailers",
  navTeam: "Team",
  tagline: "Voice-powered sales, orders and field operations.",
  landingSub: "Talk through the visit. Get a verified order, payment and follow-ups — filed only after you confirm.",
  step1: "Speak naturally in Hinglish",
  step2: "Check the draft, fix it by voice",
  step3: "Confirm — filed and read back to you",
  signIn: "Sign in",
  username: "Username",
  password: "Password",
};
export type Key = keyof typeof en;

const hinglish: Record<Key, string> = {
  hello: "Namaste",
  tabToday: "Aaj",
  tabVisits: "Visits",
  tabOrders: "Orders",
  tabMore: "Aur",
  logVisit: "Visit darj karo",
  logSub: "Visit ke baare mein bolo — dukaan, order, payment, vaade.",
  todaysVisits: "Aaj ki visits",
  followUps: "Follow-ups",
  overdue: "Late",
  booked: "ka order",
  timeSaved: "Bacha time",
  tapToRecord: "Tap karke bolo",
  orHold: "ya dabake rakho",
  recording: "Record ho raha hai",
  release: "chhodo, bhej do",
  typeInstead: "Bol nahi sakte? Likh do",
  sample: "Sample visit try karo",
  reviewVisit: "Visit dekho",
  reviewSub: "Nikali gayi details check karke confirm karo.",
  edit: "Sudhaaro",
  confirm: "Confirm",
  answerFirst: "Pehle jawab do",
  discard: "Draft hatao",
  visitSaved: "Visit Save",
  logAnother: "Agli Visit Darj Karo",
  backToToday: "Aaj par wapas",
  playReply: "Bolkar confirmation suno",
  stepListen: "Sun raha hoon",
  stepUnderstand: "Samajh raha hoon",
  stepMatch: "Match kar raha hoon",
  offline: "Offline",
  queued: "recording upload hone ka intezaar",
  signOut: "Sign out",
  language: "App ki bhasha",
  speechLanguage: "Bol rahe hain",
  noVisits: "Abhi koi visit nahi. Pehli visit darj karo.",
  noOrders: "Abhi koi order nahi.",
  done: "Ho gaya",
  waiting: "Aapka intezaar",
  nothingDue: "Sab clear. Jo vaade bologe, yahan dikhenge.",
  promisesDue: "Nibhane wale vaade",
  askTitle: "Poochho",
  askSub: "Apni team ke data se jawab pao.",
  askPlaceholder: "Kin retailers ka payment overdue hai?",
  checkOne: "Ek cheez confirm karo",
  hearIt: "Suno",
  correct: "Dabake sudhaaro",
  correctHint: "jaise “Parle-G 15 kar do”",
  youSaid: "Aapne kaha",
  areaOps: "Area Operations",
  navOverview: "Overview",
  navAsk: "Poochho",
  navOrders: "Orders",
  navPromises: "Vaade",
  navRetailers: "Retailers",
  navTeam: "Team",
  tagline: "Awaaz se sales, orders aur field operations.",
  landingSub: "Visit ke baare mein bolo. Verified order, payment aur follow-up pao — aapke confirm karne ke baad hi file hoga.",
  step1: "Hinglish mein seedha bolo",
  step2: "Draft dekho, awaaz se sudhaaro",
  step3: "Confirm karo — file hua, aur bolkar sunaya",
  signIn: "Sign in",
  username: "Username",
  password: "Password",
};

export type UiLang = "en" | "hinglish";
const KEY = "ff.ui";
const dict = { en, hinglish };

interface Ctx { lang: UiLang; setLang: (l: UiLang) => void; t: (k: Key) => string }
const I18n = createContext<Ctx>({ lang: "en", setLang: () => {}, t: (k) => en[k] });

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<UiLang>(() => {
    try { return localStorage.getItem(KEY) === "hinglish" ? "hinglish" : "en"; } catch { return "en"; }
  });
  const setLang = useCallback((l: UiLang) => {
    setLangState(l);
    try { localStorage.setItem(KEY, l); } catch { /* ignore */ }
  }, []);
  const value = useMemo<Ctx>(() => ({ lang, setLang, t: (k) => dict[lang][k] }), [lang, setLang]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);

export function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="seg seg-sm" role="radiogroup" aria-label="App language">
      <button role="radio" aria-checked={lang === "en"} className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
      <button role="radio" aria-checked={lang === "hinglish"} className={lang === "hinglish" ? "on" : ""} onClick={() => setLang("hinglish")}>हिं</button>
    </div>
  );
}
