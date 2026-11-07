import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import type { Role } from "../types";
import { MANAGER_TOUR, REP_TOUR, pick } from "./content";

const key = (userId: string) => `bb.tour.v1.${userId}`;

/** True until this user has finished or skipped the tour on this device. Storage failures count as "seen" (never nag). */
export function tourUnseen(userId: string): boolean {
  try { return localStorage.getItem(key(userId)) === null; } catch { return false; }
}
function markSeen(userId: string) {
  try { localStorage.setItem(key(userId), new Date().toISOString()); } catch { /* private mode */ }
}

/** Step-by-step welcome tour, shown automatically the first time a user signs in and replayable from Help. */
export function Tour({ role, userId, onClose }: { role: Role; userId: string; onClose: () => void }) {
  const { lang, t } = useI18n();
  const steps = role === "rep" ? REP_TOUR : MANAGER_TOUR;
  const [i, setI] = useState(0);
  const next = useRef<HTMLButtonElement>(null);
  const step = steps[i];
  const last = i === steps.length - 1;
  const close = () => { markSeen(userId); onClose(); };

  useEffect(() => { next.current?.focus(); }, [i]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="tour-scrim" role="presentation">
      <div className="tour-card" role="dialog" aria-modal="true" aria-labelledby="tour-title">
        <div className="tour-top">
          <small className="eyebrow">{i + 1} / {steps.length}</small>
          <button className="link" onClick={close}>{lang === "hinglish" ? "Skip" : "Skip tour"}</button>
        </div>
        <span className="tour-ico"><Icon name={step.icon} size={30} stroke={1.8} /></span>
        <h2 id="tour-title">{pick(lang, step.title)}</h2>
        <p>{pick(lang, step.body)}</p>
        <div className="tour-dots" aria-hidden>{steps.map((_, k) => <i key={k} className={k === i ? "on" : k < i ? "done" : ""} />)}</div>
        <div className="tour-actions">
          <button className="btn btn-outline" disabled={i === 0} onClick={() => setI(i - 1)}>{lang === "hinglish" ? "Peeche" : "Back"}</button>
          <button ref={next} className="btn btn-red grow" onClick={() => (last ? close() : setI(i + 1))}>
            {last ? (lang === "hinglish" ? "Shuru karein" : "Get started") : (lang === "hinglish" ? "Aage" : "Next")}<Icon name="arrow" size={18} />
          </button>
        </div>
        <small className="tour-foot">{t("tabMore")}: {lang === "hinglish" ? "manual aur tour kabhi bhi dobara dekho" : "the manual and this tour are always available"}</small>
      </div>
    </div>
  );
}
