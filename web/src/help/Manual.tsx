import { useState } from "react";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import type { Role } from "../types";
import { MANAGER_MANUAL, REP_MANUAL, pick } from "./content";

/** The user manual: chapters with numbered steps. Opens one chapter at a time so it stays readable on a phone. */
export function Manual({ role, onTour, onReport }: { role: Role; onTour: () => void; onReport: () => void }) {
  const { lang } = useI18n();
  const chapters = (role === "rep" ? REP_MANUAL : MANAGER_MANUAL).filter((c) => c.id !== "admin" || role === "admin");
  const [open, setOpen] = useState<string | null>(chapters[0]?.id ?? null);
  const hi = lang === "hinglish";
  return (
    <div className="manual">
      <p className="subtitle">{hi ? "BolBazaar ka poora guide, step by step." : "Step-by-step guide to using BolBazaar."}</p>
      <div className="manual-actions">
        <button className="btn btn-outline btn-sm" onClick={onTour}><Icon name="play" size={14} />{hi ? "Tour dobara dekho" : "Take the tour"}</button>
        <button className="btn btn-outline btn-sm" onClick={onReport}><Icon name="alert" size={14} />{hi ? "Bug report karo" : "Report a bug"}</button>
      </div>
      {chapters.map((c) => {
        const on = open === c.id;
        return (
          <section key={c.id} className={`chapter ${on ? "chapter-on" : ""}`}>
            <button className="chapter-head" aria-expanded={on} onClick={() => setOpen(on ? null : c.id)}>
              <b>{pick(lang, c.title)}</b><Icon name={on ? "up" : "down"} size={18} />
            </button>
            {on && (
              <div className="chapter-body">
                {c.intro && <p>{pick(lang, c.intro)}</p>}
                <ol>{c.steps.map((s, k) => <li key={k}>{pick(lang, s)}</li>)}</ol>
                {c.tip && <p className="chapter-tip"><b>{hi ? "Tip: " : "Tip: "}</b>{pick(lang, c.tip)}</p>}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
