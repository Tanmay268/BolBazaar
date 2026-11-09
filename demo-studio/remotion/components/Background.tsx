import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C } from "../lib";

/** Brand background: warm paper or ink, with a slow drifting red glow and fine line texture. */
export const Background: React.FC<{ tone?: "ink" | "paper" }> = ({ tone = "ink" }) => {
  const f = useCurrentFrame();
  const bg = tone === "ink" ? "#0e0e0f" : C.paper;
  const x = 30 + Math.sin(f / 90) * 12, y = 70 + Math.cos(f / 120) * 8;
  return (
    <AbsoluteFill style={{ background: bg }}>
      <AbsoluteFill style={{ background: `radial-gradient(60% 70% at ${x}% ${y}%, ${tone === "ink" ? "rgba(215,40,47,.22)" : "rgba(215,40,47,.10)"} 0%, rgba(0,0,0,0) 70%)` }} />
      <AbsoluteFill style={{ opacity: tone === "ink" ? 0.05 : 0.04, backgroundImage: `repeating-linear-gradient(0deg, ${tone === "ink" ? "#fff" : "#000"} 0 1px, transparent 1px 4px)` }} />
    </AbsoluteFill>
  );
};

export const BG_PAPER = C.paper;
