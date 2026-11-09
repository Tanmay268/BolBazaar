import React from "react";
import type { PlanScene } from "../types";
import { PhoneScene } from "./PhoneScene";

/** Scene 2: the rep records the visit. Real recording + waveform of the audio actually fed to the microphone. */
export const RepRecording: React.FC<{ scene: PlanScene }> = ({ scene }) => <PhoneScene scene={scene} />;
