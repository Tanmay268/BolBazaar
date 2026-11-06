import { createContext, useCallback, useContext, useMemo, useState } from "react";

const en = {
  hello: "Hello",
  today: "Today",
  tabToday: "Today",
  tabVisits: "Visits",
  tabTalk: "Talk",
  tabPromises: "Promises",
  tabYou: "You",
  logVisit: "Log a visit",
  heroSub: "Speak it once. We file it — after you confirm.",
  visitsToday: "Visits today",
  booked: "Booked today",
  saved: "Time saved (est.)",
  promisesDue: "Promises to keep",
  nothingDue: "All clear. New promises you speak will show up here.",
  waiting: "Waiting for you",
  hold: "Hold to talk",
  release: "Release to send",
  idleHint: "Tell me about the visit — retailer, order, payment, promises.",
  typeInstead: "Can't talk? Type it",
  sample: "Try a sample visit",
  understood: "Here's what I understood",
  checkOne: "One quick check",
  hearIt: "Hear it",
  correct: "Hold to correct",
  correctHint: "e.g. “make Parle-G 15”",
  confirm: "Confirm & save",
  answerFirst: "Answer the question first",
  discard: "Discard",
  visitSaved: "Visit saved",
  nextVisit: "Log another visit",
  playReply: "Play spoken confirmation",
  stepListen: "Listening",
  stepUnderstand: "Understanding",
  stepMatch: "Matching",
  offline: "Offline",
  queued: "recording(s) waiting to upload",
  signOut: "Sign out",
  language: "App language",
  speechLanguage: "Speaking in",
  noVisits: "No visits yet. Tap Talk to log your first one.",
  done: "Done",
  overdue: "overdue",
  ask: "Ask your team's data",
  overview: "Overview",
  askTab: "Ask",
  feed: "Activity",
  tagline: "Bolo. Visit file ho gayi.",
  landingSub: "The voice assistant for field sales. Talk through the visit; get a verified order, payment and follow-ups.",
  step1: "Speak naturally in Hinglish",
  step2: "Check the draft and fix it by voice",
  step3: "Confirm — it's filed, and read back to you",
  signIn: "Sign in",
  username: "Username",
  password: "Password",
  callAgent: "Call agent",
  callNow: "Call",
  hangUp: "End call",
  actAsRetailer: "Demo mode: you play the retailer. Reply by voice or type.",
  approve: "Approve & file",
  reject: "Reject",
  recentCalls: "Recent calls",
  toCall: "Retailers to call",
  calls: "Calls",
  voiceOn: "Agent voice",
};
export type Key = keyof typeof en;

const hinglish: Record<Key, string> = {
  hello: "Namaste",
  today: "Aaj",
  tabToday: "Aaj",
  tabVisits: "Visits",
  tabTalk: "Bolo",
  tabPromises: "Vaade",
  tabYou: "Aap",
  logVisit: "Visit darj karo",
  heroSub: "Ek baar bolo. Confirm karte hi file ho jayega.",
  visitsToday: "Aaj ki visits",
  booked: "Aaj ka order",
  saved: "Bacha time (anumaan)",
  promisesDue: "Nibhane wale vaade",
  nothingDue: "Sab clear. Jo vaade bologe, yahan dikhenge.",
  waiting: "Aapka intezaar",
  hold: "Dabake bolo",
  release: "Chhodo, bhej do",
  idleHint: "Visit ke baare mein bolo — dukaan, order, payment, vaade.",
  typeInstead: "Bol nahi sakte? Likh do",
  sample: "Sample visit try karo",
  understood: "Maine ye samjha",
  checkOne: "Ek cheez confirm karo",
  hearIt: "Suno",
  correct: "Dabake sudhaaro",
  correctHint: "jaise “Parle-G 15 kar do”",
  confirm: "Confirm karke save karo",
  answerFirst: "Pehle sawaal ka jawab do",
  discard: "Hatao",
  visitSaved: "Visit save ho gayi",
  nextVisit: "Agli visit darj karo",
  playReply: "Bolkar confirmation suno",
  stepListen: "Sun raha hoon",
  stepUnderstand: "Samajh raha hoon",
  stepMatch: "Match kar raha hoon",
  offline: "Offline",
  queued: "recording upload hone ka intezaar",
  signOut: "Sign out",
  language: "App ki bhasha",
  speechLanguage: "Bol rahe hain",
  noVisits: "Abhi koi visit nahi. Bolo dabake pehli visit darj karo.",
  done: "Ho gaya",
  overdue: "late",
  ask: "Apni team ka data poochho",
  overview: "Overview",
  askTab: "Poochho",
  feed: "Activity",
  tagline: "Bolo. Visit file ho gayi.",
  landingSub: "Field sales ka voice assistant. Visit ke baare mein bolo; verified order, payment aur follow-up pao.",
  step1: "Hinglish mein seedha bolo",
  step2: "Draft dekho, awaaz se sudhaaro",
  step3: "Confirm karo — file ho gaya, aur bolkar sunaya bhi",
  signIn: "Sign in",
  username: "Username",
  password: "Password",
  callAgent: "Call agent",
  callNow: "Call karo",
  hangUp: "Call khatam",
  actAsRetailer: "Demo mode: aap retailer ban ke jawab do. Bolke ya likhke.",
  approve: "Approve karke file karo",
  reject: "Reject",
  recentCalls: "Haal ki calls",
  toCall: "Call karne wale retailer",
  calls: "Calls",
  voiceOn: "Agent ki awaaz",
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
