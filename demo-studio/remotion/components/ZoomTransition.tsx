import React from "react";
import { useCurrentFrame } from "remotion";
import { C, easeIO, tween } from "../lib";

/**
 * Scene-boundary wipe: a red slab sweeps in over the old scene and out over the new one.
 * Rendered in the root timeline, centred on the boundary frame.
 */
export const ZoomTransition: React.FC<{ at: number; half?: number; width: number }> = ({ at, half = 9, width }) => {
  const f = useCurrentFrame();
  if (f < at - half || f > at + half) return null;
  const p = f < at ? tween(f, at - half, at, 0, 1, easeIO) : tween(f, at, at + half, 1, 2, easeIO);
  // 0..1 covers the screen left->right, 1..2 uncovers it left->right
  const left = p <= 1 ? 0 : (p - 1) * width;
  const right = p <= 1 ? (1 - p) * width : 0;
  return (
    <div style={{ position: "absolute", top: 0, bottom: 0, left, right, background: C.red, zIndex: 50, boxShadow: "0 0 80px rgba(0,0,0,.4)" }} />
  );
};
