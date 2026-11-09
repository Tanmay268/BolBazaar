import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { PlanScene } from "../types";
import { C, FONT, ease, tween } from "../lib";
import { Background } from "../components/Background";
import { LogoMark, Wordmark } from "../components/Logo";
import { Subtitle } from "../components/Subtitle";

/** Scene 1: cinematic brand intro. */
export const Intro: React.FC<{ scene: PlanScene }> = ({ scene }) => {
  const f = useCurrentFrame();
  const reveal = tween(f, 4, 50, 0, 1);
  const word = tween(f, 34, 66, 0, 1);
  const lines = ["Speak the visit.", "Skip the form."];
  const zoom = 1 + tween(f, 0, scene.durF, 0, 0.08);
  return (
    <AbsoluteFill>
      <Background tone="ink" />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `scale(${zoom})` }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 46 }}>
          <LogoMark size={190} reveal={reveal} live={f > 56} />
          <Wordmark size={150} reveal={word} />
          <div style={{ fontFamily: FONT, fontSize: 40, fontWeight: 600, color: "rgba(255,255,255,.82)", letterSpacing: ".01em", display: "flex", gap: 22 }}>
            {lines.map((l, i) => {
              const o = ease(tween(f, 78 + i * 14, 98 + i * 14, 0, 1));
              return <span key={l} style={{ opacity: o, transform: `translateY(${(1 - o) * 16}px)`, color: i === 1 ? "#fff" : undefined }}>{l}</span>;
            })}
          </div>
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 150, textAlign: "center", fontFamily: FONT, color: C.red, fontSize: 22, fontWeight: 800, letterSpacing: ".3em", opacity: ease(tween(f, 100, 120, 0, 1)) }}>VOICE-FIRST FIELD SALES</div>
      <Subtitle subs={scene.subs} />
    </AbsoluteFill>
  );
};
