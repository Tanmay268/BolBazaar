import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { PlanScene } from "../types";
import { C, FONT, ease, tween } from "../lib";
import { Background } from "../components/Background";
import { AppStage, WaveCard } from "../components/AppStage";
import { LowerThird } from "../components/LowerThird";
import { Subtitle } from "../components/Subtitle";

/** Shared layout for the rep scenes: real phone recording on the left, scene message on the right. */
export const PhoneScene: React.FC<{ scene: PlanScene }> = ({ scene }) => {
  const f = useCurrentFrame();
  const active = scene.highlights.find((h) => f >= h.fromF && f < h.toF)?.label;
  const words = scene.headline.split(" ");
  return (
    <AbsoluteFill>
      <Background tone="ink" />
      <LowerThird step={scene.step} title={scene.title} />
      <AppStage scene={scene} scale={0.8} gx={600 - (430 * 0.8) / 2} gy={124} kind="phone" />
      <div style={{ position: "absolute", left: 1040, top: 200, width: 790, fontFamily: FONT }}>
        <div style={{ color: C.red, fontWeight: 800, fontSize: 24, letterSpacing: ".22em", textTransform: "uppercase", opacity: ease(tween(f, 6, 22, 0, 1)) }}>{scene.kicker}</div>
        <div style={{ marginTop: 18, color: "#fff", fontWeight: 900, fontSize: 92, lineHeight: 0.98, letterSpacing: "-0.04em" }}>
          {words.map((w, i) => {
            const o = ease(tween(f, 10 + i * 3, 26 + i * 3, 0, 1));
            return <span key={i} style={{ display: "inline-block", marginRight: 22, opacity: o, transform: `translateY(${(1 - o) * 30}px)` }}>{w}</span>;
          })}
        </div>
        {scene.body && <div style={{ marginTop: 26, color: "rgba(255,255,255,.7)", fontSize: 30, lineHeight: 1.4, maxWidth: 700, opacity: ease(tween(f, 26, 44, 0, 1)) }}>{scene.body}</div>}
        {scene.chips && (
          <div style={{ marginTop: 38, display: "flex", flexWrap: "wrap", gap: 12, maxWidth: 760 }}>
            {scene.chips.map((c, i) => {
              const on = active === c;
              return (
                <span key={c} style={{ padding: "10px 20px", fontSize: 24, fontWeight: 700, borderRadius: 40, border: `2px solid ${on ? C.red : "rgba(255,255,255,.22)"}`, background: on ? C.red : "transparent", color: "#fff", opacity: ease(tween(f, 30 + i * 4, 46 + i * 4, 0, 1)), transform: `scale(${on ? 1.06 : 1})`, transition: "none" }}>{c}</span>
              );
            })}
          </div>
        )}
        {scene.badges.filter((b) => f >= b.fromF && f < b.toF).map((b, i) => (
          <div key={i} style={{ marginTop: 28, display: "inline-block", padding: "14px 24px", background: C.paper, color: C.ink, fontWeight: 800, fontSize: 26, borderLeft: `8px solid ${C.red}`, opacity: ease(tween(f, b.fromF, b.fromF + 10, 0, 1)) }}>{b.text}</div>
        ))}
      </div>
      <WaveCard scene={scene} x={1040} y={650} w={640} />
      <Subtitle subs={scene.subs} />
    </AbsoluteFill>
  );
};
