import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import type { Plan, PlanScene } from "./types";
import { clamp } from "./lib";
import { Progress } from "./components/LowerThird";
import { ZoomTransition } from "./components/ZoomTransition";
import { Intro } from "./scenes/Intro";
import { RepRecording } from "./scenes/RepRecording";
import { ExtractedOrder } from "./scenes/ExtractedOrder";
import { VoiceCorrection } from "./scenes/VoiceCorrection";
import { Confirmation } from "./scenes/Confirmation";
import { ManagerDashboard } from "./scenes/ManagerDashboard";
import { Outro } from "./scenes/Outro";

const MUSIC_BASE = 0.2, MUSIC_DUCK = 0.065;

/** Music volume for global frame f: faded in/out, ducked while narration speaks (with smooth 10-frame ramps). */
export const musicVolume = (plan: Plan, f: number): number => {
  let duck = 0;
  for (const n of plan.narration) {
    const a = n.startF, b = n.startF + n.durF;
    const k = f < a ? Math.max(0, 1 - (a - f) / 10) : f > b ? Math.max(0, 1 - (f - b) / 14) : 1;
    duck = Math.max(duck, k);
  }
  const fadeIn = Math.min(1, f / 30), fadeOut = Math.min(1, (plan.totalF - f) / 60);
  return Math.max(0, (MUSIC_BASE + (MUSIC_DUCK - MUSIC_BASE) * duck) * Math.min(fadeIn, fadeOut));
};

const renderScene = (s: PlanScene, plan: Plan) => {
  switch (s.id) {
    case "intro": return <Intro scene={s} />;
    case "rep": return <RepRecording scene={s} />;
    case "extraction": return <ExtractedOrder scene={s} />;
    case "correction": return <VoiceCorrection scene={s} />;
    case "confirmation": return <Confirmation scene={s} />;
    case "manager": return <ManagerDashboard scene={s} />;
    default: return <Outro scene={s} website={plan.websiteUrl} />;
  }
};

export const DemoComposition: React.FC<{ plan: Plan }> = ({ plan }) => {
  const f = useCurrentFrame();
  const ticks = plan.scenes.slice(1).map((s) => s.startF);
  return (
    <AbsoluteFill style={{ background: "#0e0e0f" }}>
      {plan.scenes.map((s) => (
        <Sequence key={s.id} from={s.startF} durationInFrames={s.durF}>{renderScene(s, plan)}</Sequence>
      ))}
      {ticks.map((t) => <ZoomTransition key={t} at={t} width={plan.width} />)}
      {f > 20 && f < plan.totalF - 150 && <Progress frame={f} total={plan.totalF} ticks={ticks} />}
      {/* narration, one clip per line */}
      {plan.narration.map((n, i) => (
        <Sequence key={i} from={n.startF} durationInFrames={n.durF + 2}><Audio src={staticFile(n.src)} volume={1} /></Sequence>
      ))}
      {plan.sfx.map((x, i) => <Sequence key={`s${i}`} from={x.startF}><Audio src={staticFile(x.src)} volume={x.volume} /></Sequence>)}
      <Audio src={staticFile(plan.music)} loop volume={(frame) => musicVolume(plan, frame)} />
    </AbsoluteFill>
  );
};

export const _clamp = clamp;
