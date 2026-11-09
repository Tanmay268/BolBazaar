import React from "react";
import { useCurrentFrame } from "remotion";
import { C, FONT, LOGO_ENV, ease, tween } from "../lib";

/** The 11-bar BolBazaar waveform mark. `live` makes the bars move like a voice signal. */
export const LogoMark: React.FC<{ size: number; reveal?: number; live?: boolean; onDark?: boolean }> = ({ size, reveal = 1, live = false, onDark = true }) => {
  const f = useCurrentFrame();
  const n = LOGO_ENV.length, w = size / (n * 1.9), gap = w * 0.9;
  return (
    <div style={{ display: "flex", alignItems: "center", gap, height: size, filter: onDark ? "drop-shadow(0 0 24px rgba(215,40,47,.45))" : undefined }}>
      {LOGO_ENV.map((e, i) => {
        const appear = tween(reveal, i / (n * 1.6), i / (n * 1.6) + 0.45, 0, 1);
        const wob = live ? 1 + 0.28 * Math.sin(f / 4 + i * 1.3) : 1;
        return <div key={i} style={{ width: w, height: size * e * 0.8 * wob * appear, borderRadius: w, background: `linear-gradient(#ee4a4c, ${C.redInk})` }} />;
      })}
    </div>
  );
};

export const Wordmark: React.FC<{ size: number; color?: string; reveal?: number }> = ({ size, color = "#fff", reveal = 1 }) => (
  <div style={{ fontFamily: FONT, fontWeight: 900, fontSize: size, letterSpacing: "-0.045em", color, display: "flex", alignItems: "flex-start", lineHeight: 1, opacity: ease(reveal), transform: `translateY(${(1 - ease(reveal)) * 24}px)` }}>
    BolBazaar
    <svg width={size * 0.42} height={size * 0.42} viewBox="0 0 24 24" fill="none" stroke={C.red} strokeWidth="2.8" strokeLinecap="square" style={{ marginLeft: size * 0.04, marginTop: size * 0.04 }}><path d="M7 17L17 7M8 7h9v9" /></svg>
  </div>
);
