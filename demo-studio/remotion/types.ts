export interface Box { x: number; y: number; w: number; h: number }
/** Maps scene frames [startF, startF+durF) to recording time. rate 1 = real time; freeze holds one frame. */
export interface Seg { src: string; srcFrom: number; rate: number; startF: number; durF: number; freeze?: boolean }
export interface CursorKey { f: number; x: number; y: number }
export interface ClickEv { f: number; x: number; y: number }
export interface HLight { fromF: number; toF: number; box: Box; label: string }
export interface ZoomKey { f: number; scale: number; cx: number; cy: number }
export interface Sub { text: string; fromF: number; toF: number }
export interface WaveSpec { samples: number[]; perSec: number; recStartSrc: number; recEndSrc: number; src: string }
export interface Badge { fromF: number; toF: number; text: string }
export type Layout = "brand" | "phone" | "desktop";
export interface PlanScene {
  id: string; title: string; step: number; startF: number; durF: number; layout: Layout;
  viewport?: { width: number; height: number };
  segs: Seg[]; cursor: CursorKey[]; clicks: ClickEv[]; highlights: HLight[]; zooms: ZoomKey[];
  wave?: WaveSpec; subs: Sub[]; kicker: string; headline: string; body?: string; chips?: string[]; badges: Badge[];
}
export interface Plan {
  fps: number; width: number; height: number; totalF: number; scenes: PlanScene[];
  narration: { src: string; startF: number; durF: number }[];
  music: string; sfx: { src: string; startF: number; volume: number }[];
  websiteUrl?: string; modeNote?: string;
}
