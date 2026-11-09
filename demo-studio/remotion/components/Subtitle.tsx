import React from "react";
import { useCurrentFrame } from "remotion";
import type { Sub } from "../types";
import { FONT, ease, tween } from "../lib";

/** English subtitles: max two lines, bottom-safe, soft backing plate for contrast. */
export const Subtitle: React.FC<{ subs: Sub[] }> = ({ subs }) => {
  const f = useCurrentFrame();
  const s = subs.find((x) => f >= x.fromF && f < x.toF);
  if (!s) return null;
  const inO = tween(f, s.fromF, s.fromF + 6, 0, 1), outO = tween(f, s.toF - 5, s.toF, 1, 0);
  const o = Math.min(inO, outO);
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 56, display: "flex", justifyContent: "center", opacity: o, transform: `translateY(${(1 - ease(inO)) * 12}px)` }}>
      <div style={{ maxWidth: 1240, padding: "14px 30px", borderRadius: 14, background: "rgba(10,10,10,.82)", color: "#fff", fontFamily: FONT, fontWeight: 600, fontSize: 38, lineHeight: 1.28, textAlign: "center", letterSpacing: "-0.01em", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {s.text}
      </div>
    </div>
  );
};
