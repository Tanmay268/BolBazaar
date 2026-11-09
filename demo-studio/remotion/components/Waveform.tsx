import React from "react";
import { C } from "../lib";

/** Bars driven by the envelope of the real audio fixture that the app is hearing. */
export const Waveform: React.FC<{ samples: number[]; perSec: number; t: number; bars?: number; width: number; height: number; color?: string }> = ({ samples, perSec, t, bars = 48, width, height, color = C.red }) => {
  const w = width / bars;
  const i0 = Math.floor(t * perSec);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: w * 0.35, width, height }}>
      {Array.from({ length: bars }, (_, k) => {
        const idx = i0 - (bars - 1 - k);
        const v = idx >= 0 && idx < samples.length ? samples[idx] : 0.04;
        return <div key={k} style={{ width: w * 0.65, height: Math.max(4, v * height), borderRadius: w, background: color, opacity: 0.35 + 0.65 * (k / bars) }} />;
      })}
    </div>
  );
};
