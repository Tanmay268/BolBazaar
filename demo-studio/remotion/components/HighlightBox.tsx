import React from "react";
import { useCurrentFrame } from "remotion";
import type { HLight } from "../types";
import { C, ease, tween } from "../lib";

/** Animated focus box around a real element (coordinates come from the recorded DOM, never invented). */
export const HighlightBox: React.FC<{ items: HLight[] }> = ({ items }) => {
  const f = useCurrentFrame();
  return (
    <>
      {items.filter((h) => f >= h.fromF && f < h.toF).map((h, i) => {
        const inK = ease(tween(f, h.fromF, h.fromF + 9, 0, 1)), outK = tween(f, h.toF - 6, h.toF, 1, 0);
        const pad = 6 + (1 - inK) * 14, pulse = 0.5 + 0.5 * Math.sin((f - h.fromF) / 5);
        return (
          <div key={i} style={{ position: "absolute", left: h.box.x - pad, top: h.box.y - pad, width: h.box.w + pad * 2, height: h.box.h + pad * 2, borderRadius: 10, border: `3px solid ${C.red}`, boxShadow: `0 0 0 ${3 + pulse * 5}px rgba(215,40,47,.18), 0 0 28px rgba(215,40,47,.45)`, opacity: Math.min(inK, outK), pointerEvents: "none" }} />
        );
      })}
    </>
  );
};
