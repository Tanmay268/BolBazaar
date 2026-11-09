import { Easing, interpolate } from "remotion";

export const C = { red: "#d7282f", redInk: "#b81f26", ink: "#111111", paper: "#f5f3ed", paper2: "#ece9e1", hair: "#d4d0c5", white: "#ffffff" };
export const FONT = '"Helvetica Neue", Helvetica, Arial, "Noto Sans Devanagari", system-ui, sans-serif';
export const ease = Easing.bezier(0.22, 1, 0.36, 1);
export const easeIO = Easing.bezier(0.65, 0, 0.35, 1);
export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const tween = (f: number, a: number, b: number, from: number, to: number, e: (t: number) => number = ease) =>
  interpolate(f, [a, b], [from, to], { ...clamp, easing: e });
/** Resting silhouette of the BolBazaar logo (same as the web app's launch intro). */
export const LOGO_ENV = [0.3, 0.5, 0.72, 0.6, 0.92, 1, 0.84, 0.68, 0.74, 0.5, 0.3];
