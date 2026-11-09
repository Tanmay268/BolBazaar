import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { PlanScene } from "../types";
import { C, FONT, ease, tween } from "../lib";
import { Background } from "../components/Background";
import { AppStage } from "../components/AppStage";
import { LowerThird } from "../components/LowerThird";
import { Subtitle } from "../components/Subtitle";

/** Scene 6: the real manager dashboard and a real question answered from the database. */
export const ManagerDashboard: React.FC<{ scene: PlanScene }> = ({ scene }) => {
  const f = useCurrentFrame();
  const S = 0.68;
  return (
    <AbsoluteFill>
      <Background tone="ink" />
      <LowerThird step={scene.step} title={scene.title} />
      <div style={{ position: "absolute", right: 64, top: 44, fontFamily: FONT, color: C.red, fontWeight: 800, fontSize: 24, letterSpacing: ".22em", textTransform: "uppercase", opacity: ease(tween(f, 8, 24, 0, 1)) }}>{scene.kicker}</div>
      <AppStage scene={scene} scale={S} gx={(1920 - 1920 * S) / 2} gy={112} kind="desktop" />
      <Subtitle subs={scene.subs} />
    </AbsoluteFill>
  );
};
