import React from "react";
import { useCurrentFrame } from "remotion";
import { C, FONT, ease, tween } from "../lib";

/** Step tag in the top-left corner, for example "02  EXTRACTION". */
export const LowerThird: React.FC<{ step: number; title: string; tone?: "ink" | "paper" }> = ({ step, title, tone = "ink" }) => {
  const f = useCurrentFrame();
  const o = ease(tween(f, 4, 20, 0, 1));
  const fg = tone === "ink" ? "#fff" : C.ink;
  return (
    <div style={{ position: "absolute", left: 64, top: 44, display: "flex", alignItems: "center", gap: 16, fontFamily: FONT, opacity: o, transform: `translateX(${(1 - o) * -30}px)` }}>
      <span style={{ background: C.red, color: "#fff", fontWeight: 800, fontSize: 24, padding: "6px 14px", letterSpacing: ".04em" }}>{String(step).padStart(2, "0")}</span>
      <span style={{ color: fg, fontWeight: 800, fontSize: 26, letterSpacing: ".14em", textTransform: "uppercase" }}>{title}</span>
    </div>
  );
};

/** Thin progress indicator with one tick per scene. */
export const Progress: React.FC<{ frame: number; total: number; ticks: number[] }> = ({ frame, total, ticks }) => (
  <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 6, background: "rgba(255,255,255,.08)" }}>
    <div style={{ height: "100%", width: `${(frame / total) * 100}%`, background: C.red }} />
    {ticks.map((t, i) => <i key={i} style={{ position: "absolute", left: `${(t / total) * 100}%`, top: 0, width: 2, height: 6, background: "rgba(255,255,255,.55)" }} />)}
  </div>
);
