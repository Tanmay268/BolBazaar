import React from "react";
import { Composition } from "remotion";
import { DemoComposition } from "./DemoComposition";
import type { Plan } from "./types";

const empty: Plan = { fps: 30, width: 1920, height: 1080, totalF: 30, scenes: [], narration: [], music: "", sfx: [] };

export const Root: React.FC = () => (
  <Composition
    id="BolBazaarDemo"
    component={DemoComposition as React.FC<Record<string, unknown>>}
    width={1920} height={1080} fps={30} durationInFrames={30}
    defaultProps={{ plan: empty } as Record<string, unknown>}
    calculateMetadata={({ props }) => {
      const plan = (props as { plan: Plan }).plan;
      return { durationInFrames: Math.max(30, plan.totalF), width: plan.width, height: plan.height, fps: plan.fps };
    }}
  />
);
