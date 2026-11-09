import React from "react";
import type { PlanScene } from "../types";
import { PhoneScene } from "./PhoneScene";

/** Scene 3: the extracted visit. Highlights follow the real rows of the recorded review screen. */
export const ExtractedOrder: React.FC<{ scene: PlanScene }> = ({ scene }) => <PhoneScene scene={scene} />;
