import React from "react";
import { Freeze, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { PlanScene, ZoomKey } from "../types";
import { C, FONT, ease, easeIO, tween } from "../lib";
import { AnimatedCursor } from "./AnimatedCursor";
import { HighlightBox } from "./HighlightBox";
import { Waveform } from "./Waveform";

/** Recording time at a scene frame, following the piecewise segment mapping. */
export const srcTimeAt = (scene: PlanScene, f: number): number => {
  const s = scene.segs.find((x) => f >= x.startF && f < x.startF + x.durF) ?? scene.segs[scene.segs.length - 1];
  if (!s) return 0;
  return s.freeze ? s.srcFrom : s.srcFrom + ((Math.min(f, s.startF + s.durF) - s.startF) / 30) * s.rate;
};

const zoomAt = (keys: ZoomKey[], f: number) => {
  if (!keys.length) return { z: 1, cx: 0, cy: 0 };
  if (f <= keys[0].f) return { z: keys[0].scale, cx: keys[0].cx, cy: keys[0].cy };
  for (let i = 1; i < keys.length; i++) {
    if (f <= keys[i].f) {
      const a = keys[i - 1], b = keys[i], k = easeIO(Math.min(1, Math.max(0, (f - a.f) / Math.max(1, b.f - a.f))));
      return { z: a.scale + (b.scale - a.scale) * k, cx: a.cx + (b.cx - a.cx) * k, cy: a.cy + (b.cy - a.cy) * k };
    }
  }
  const l = keys[keys.length - 1];
  return { z: l.scale, cx: l.cx, cy: l.cy };
};

/**
 * Real screen recording shown inside a device frame, with a camera-style zoom, focus boxes, a drawn cursor and
 * (for the rep scenes) a waveform of the real audio fixture. Nothing here alters or re-creates UI content.
 */
export const AppStage: React.FC<{ scene: PlanScene; scale: number; gx: number; gy: number; kind: "phone" | "desktop" }> = ({ scene, scale: S, gx, gy, kind }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const vp = scene.viewport!;
  const W = vp.width * S, H = vp.height * S;
  const { z, cx, cy } = zoomAt(scene.zooms, f);
  const k = Math.min(1, Math.max(0, (z - 1) / 0.5));
  // keep the zoom focus point at the centre of the screen
  const dx = (vp.width / 2 - cx) * k, dy = (vp.height / 2 - cy) * k;
  const bez = kind === "phone" ? 14 : 0;
  const push = 1 + tween(f, 0, scene.durF, 0, 0.035, easeIO);
  const enter = ease(tween(f, 0, 22, 0, 1));
  return (
    <div style={{ position: "absolute", left: gx - bez, top: gy - bez, width: W + bez * 2, height: H + bez * 2 + (kind === "desktop" ? 34 : 0), transform: `scale(${push}) translateY(${(1 - enter) * 40}px)`, opacity: enter, transformOrigin: "50% 50%",
      background: kind === "phone" ? "#050505" : "#1b1b1c", borderRadius: kind === "phone" ? 54 : 16, boxShadow: "0 40px 90px rgba(0,0,0,.55), 0 0 0 2px rgba(255,255,255,.07)" }}>
      {kind === "desktop" && (
        <div style={{ height: 34, display: "flex", alignItems: "center", gap: 8, paddingLeft: 16 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <i key={c} style={{ width: 11, height: 11, borderRadius: 11, background: c, opacity: 0.85 }} />)}
          <span style={{ marginLeft: 14, fontFamily: FONT, fontSize: 14, color: "rgba(255,255,255,.55)", letterSpacing: ".04em" }}>BolBazaar - Manager</span>
        </div>
      )}
      <div style={{ position: "absolute", left: bez, top: bez + (kind === "desktop" ? 34 : 0), width: W, height: H, overflow: "hidden", borderRadius: kind === "phone" ? 42 : kind === "desktop" ? "0 0 14px 14px" : 0, background: C.paper }}>
        <div style={{ width: vp.width, height: vp.height, transform: `scale(${S})`, transformOrigin: "0 0" }}>
          <div style={{ width: vp.width, height: vp.height, position: "relative", transformOrigin: `${cx}px ${cy}px`, transform: `translate(${dx}px, ${dy}px) scale(${z})` }}>
            {scene.segs.map((s, i) => (
              <Sequence key={i} from={s.startF} durationInFrames={Math.max(1, s.durF)} layout="none">
                {s.freeze ? (
                  <Freeze frame={0}><OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.srcFrom * fps)} muted style={{ width: vp.width, height: vp.height }} /></Freeze>
                ) : (
                  <OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.srcFrom * fps)} playbackRate={s.rate} muted style={{ width: vp.width, height: vp.height }} />
                )}
              </Sequence>
            ))}
            <HighlightBox items={scene.highlights} />
            <AnimatedCursor keys={scene.cursor} clicks={scene.clicks} scale={S * z} />
          </div>
        </div>
      </div>
    </div>
  );
};

/** Waveform card for the moment the real fixture audio is being recorded. */
export const WaveCard: React.FC<{ scene: PlanScene; x: number; y: number; w: number }> = ({ scene, x, y, w }) => {
  const f = useCurrentFrame();
  const wv = scene.wave;
  if (!wv) return null;
  const t = srcTimeAt(scene, f);
  const live = t >= wv.recStartSrc && t <= wv.recEndSrc;
  const o = ease(tween(f, 0, 1, 0, 1)) * (live ? 1 : 0.0);
  if (o <= 0) return null;
  const at = Math.max(0, t - wv.recStartSrc);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, padding: "22px 26px", borderRadius: 18, background: "rgba(255,255,255,.06)", border: "1px solid rgba(255,255,255,.14)", opacity: o, fontFamily: FONT }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, color: "#fff", fontWeight: 800, letterSpacing: ".16em", fontSize: 18 }}>
        <i style={{ width: 14, height: 14, borderRadius: 14, background: C.red, boxShadow: `0 0 ${8 + 8 * Math.sin(f / 4)}px ${C.red}` }} />
        LISTENING
        <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums", opacity: 0.75 }}>{`00:${String(Math.floor(at)).padStart(2, "0")}`}</span>
      </div>
      <div style={{ marginTop: 16 }}><Waveform samples={wv.samples} perSec={wv.perSec} t={at} bars={56} width={w - 52} height={84} /></div>
    </div>
  );
};
