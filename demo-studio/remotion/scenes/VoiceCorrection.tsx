import React from "react";
import type { PlanScene } from "../types";
import { PhoneScene } from "./PhoneScene";

/** Scene 4: correction. The old and new values are both real frames from the recording (see zoom keys). */
export const VoiceCorrection: React.FC<{ scene: PlanScene }> = ({ scene }) => <PhoneScene scene={scene} />;
