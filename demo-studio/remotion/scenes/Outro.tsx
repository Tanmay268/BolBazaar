import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { PlanScene } from "../types";
import { C, FONT, ease, tween } from "../lib";
import { Background } from "../components/Background";
import { LogoMark, Wordmark } from "../components/Logo";
import { Subtitle } from "../components/Subtitle";

/** Scene 7: closing lockup, tagline and (when configured) the website. */
export const Outro: React.FC<{ scene: PlanScene; website?: string }> = ({ scene, website }) => {
  const f = useCurrentFrame();
  const lines = ["Less typing.", "Better visibility.", "More productive sales teams."];
  const fade = tween(f, scene.durF - 20, scene.durF, 1, 0.0);
  return (
    <AbsoluteFill style={{ opacity: Math.max(fade, 0.0) }}>
      <Background tone="ink" />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 36 }}>
          <LogoMark size={130} reveal={tween(f, 2, 36, 0, 1)} live />
          <Wordmark size={118} reveal={tween(f, 20, 50, 0, 1)} />
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, fontFamily: FONT, fontWeight: 700, fontSize: 44, color: "#fff" }}>
            {lines.map((l, i) => {
              const o = ease(tween(f, 44 + i * 16, 64 + i * 16, 0, 1));
              return <span key={l} style={{ opacity: o, transform: `translateY(${(1 - o) * 18}px)`, color: i === 2 ? C.red : "#fff" }}>{l}</span>;
            })}
          </div>
          {website && <div style={{ fontFamily: FONT, fontSize: 30, fontWeight: 700, color: "rgba(255,255,255,.8)", letterSpacing: ".06em", opacity: ease(tween(f, 100, 120, 0, 1)) }}>{website}</div>}
        </div>
      </AbsoluteFill>
      <Subtitle subs={scene.subs} />
    </AbsoluteFill>
  );
};
