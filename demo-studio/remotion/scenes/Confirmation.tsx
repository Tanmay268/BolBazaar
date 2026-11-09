import React from "react";
import type { PlanScene } from "../types";
import { PhoneScene } from "./PhoneScene";

/** Scene 5: the rep confirms; only then does the app save the order. */
export const Confirmation: React.FC<{ scene: PlanScene }> = ({ scene }) => <PhoneScene scene={scene} />;
