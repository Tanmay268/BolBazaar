import React from "react";
import { useCurrentFrame } from "remotion";
import type { ClickEv, CursorKey } from "../types";
import { C, easeIO, tween } from "../lib";

const at = (keys: CursorKey[], f: number) => {
  if (!keys.length) return null;
  if (f <= keys[0].f) return keys[0];
  for (let i = 1; i < keys.length; i++) {
    if (f <= keys[i].f) {
      const a = keys[i - 1], b = keys[i], k = easeIO(Math.min(1, Math.max(0, (f - a.f) / Math.max(1, b.f - a.f))));
      return { f, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
    }
  }
  return keys[keys.length - 1];
};

/** Cursor and click ripple, positioned in recording coordinates (the parent applies stage scale and zoom). */
export const AnimatedCursor: React.FC<{ keys: CursorKey[]; clicks: ClickEv[]; scale?: number }> = ({ keys, clicks, scale = 1 }) => {
  const f = useCurrentFrame();
  const p = at(keys, f);
  if (!p || f < keys[0].f - 4) return null;
  const last = clicks.filter((c) => c.f <= f).pop();
  const since = last ? f - last.f : 99;
  const press = since < 6 ? 0.86 : 1;
  return (
    <>
      {last && since < 18 && (
        <div style={{ position: "absolute", left: last.x - 30, top: last.y - 30, width: 60, height: 60, borderRadius: 60, border: `3px solid ${C.red}`, opacity: tween(since, 0, 18, 0.9, 0), transform: `scale(${tween(since, 0, 18, 0.3, 1.5)})` }} />
      )}
      <svg width={34 / scale} height={34 / scale} viewBox="0 0 24 24" style={{ position: "absolute", left: p.x - 3, top: p.y - 2, transform: `scale(${press})`, transformOrigin: "3px 2px", filter: "drop-shadow(0 3px 5px rgba(0,0,0,.45))" }}>
        <path d="M4 2l15 9-6.5 1.6L16 20l-3 1.3-3.4-7.6L5.5 17z" fill="#fff" stroke="#111" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </>
  );
};
