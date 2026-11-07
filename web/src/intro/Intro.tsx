import { useEffect, useRef, useState } from "react";
import "./intro.css";

/**
 * Launch intro (web + Capacitor APK share this bundle).
 * Timeline: waveform logo blooms in at centre and grows -> bars come alive like a live voice signal
 * (loader) -> the mark swells and dissolves into the app.
 */

const T_HOLD = 3.4, T_OUT = 0.7; // seconds: earliest exit moment, exit duration
// Resting silhouette of the logo: symmetric, low at the edges, tallest near the middle.
const ENV = [0.3, 0.5, 0.72, 0.6, 0.92, 1, 0.84, 0.68, 0.74, 0.5, 0.3];
const N = ENV.length;

const clamp01 = (t: number) => Math.max(0, Math.min(1, t));
const easeOut = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);
const easeIO = (t: number) => { t = clamp01(t); return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
const easeBack = (t: number) => { t = clamp01(t); const c = 1.4; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };

const FREEZE = Number(new URLSearchParams(location.search).get("introT") ?? -1); // debug: freeze the timeline at N seconds

interface Props { onDone: () => void; ready?: boolean }

export function Intro({ onDone, ready = true }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const bar = useRef<HTMLSpanElement>(null);
  const readyRef = useRef(ready);
  readyRef.current = ready;
  const [gone, setGone] = useState(false);

  useEffect(() => {
    const canvas = cv.current!, ctx = canvas.getContext("2d")!;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { onDone(); setGone(true); return; }
    let w = 0, h = 0, dpr = 1, raf = 0, t0 = 0, exitAt = -1, finished = false;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth; h = window.innerHeight;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    };
    resize();
    window.addEventListener("resize", resize);

    const frame = (now: number) => {
      if (!t0) t0 = now;
      const t = FREEZE >= 0 ? FREEZE : (now - t0) / 1000;
      if (exitAt < 0 && t >= T_HOLD && readyRef.current) exitAt = t;
      const ex = exitAt < 0 ? 0 : clamp01((t - exitAt) / T_OUT);

      const cx = w / 2, cy = h / 2 - h * 0.025;
      const W0 = Math.min(w * 0.46, 260); // logo width at rest
      const appear = easeOut(t / 0.8);
      const grow = easeIO((t - 0.2) / 1.5);
      const scale = (0.62 + 0.38 * grow) * (0.9 + 0.1 * appear) * (1 + easeIO(ex) * 0.7);
      const alpha = appear * (1 - clamp01((ex - 0.25) / 0.75));
      const Wd = W0 * scale;
      const bw = Wd / (N * 1.62), gap = bw * 0.62, maxH = Wd * 0.62;
      const x0 = cx - (N * bw + (N - 1) * gap) / 2;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";

      // soft bloom behind the mark, breathing slowly
      const breathe = 0.85 + 0.15 * Math.sin(t * 2.2);
      const R = Wd * 1.25;
      const bloom = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
      bloom.addColorStop(0, `rgba(215,40,47,${0.09 * alpha * breathe})`);
      bloom.addColorStop(0.5, `rgba(215,40,47,${0.03 * alpha})`);
      bloom.addColorStop(1, "rgba(215,40,47,0)");
      ctx.fillStyle = bloom; ctx.fillRect(0, 0, w, h);

      // bars: grow from the centre outward, then ripple like a live voice signal
      const live = clamp01((t - 1.0) / 0.8);
      for (let i = 0; i < N; i++) {
        const d = Math.abs(i - (N - 1) / 2) / ((N - 1) / 2); // 0 centre .. 1 edge
        const inP = easeBack((t - 0.25 - d * 0.35) / 0.7);
        // two travelling waves with different speed so the motion never looks looped
        const wave = 0.5 + 0.5 * Math.sin(t * 4.2 - i * 0.75) * 0.65 + 0.5 * 0.35 * Math.sin(t * 6.3 + i * 1.3);
        const k = ENV[i] * (1 - live + live * (0.34 + 0.66 * clamp01(wave)));
        const bh = Math.max(bw, maxH * k * inP);
        const x = x0 + i * (bw + gap), y = cy - bh / 2;
        const g = ctx.createLinearGradient(0, y, 0, y + bh);
        g.addColorStop(0, `rgba(238,74,76,${alpha})`);
        g.addColorStop(0.55, `rgba(223,45,52,${alpha})`);
        g.addColorStop(1, `rgba(184,31,38,${alpha})`);
        ctx.shadowColor = `rgba(215,40,47,${0.28 * alpha})`; ctx.shadowBlur = bw * 0.9;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.roundRect(x, y, bw, bh, bw / 2); ctx.fill();
      }
      ctx.shadowBlur = 0;

      // loader bar eases toward ~92%, completes on exit
      if (bar.current) {
        const p = ex > 0 ? 1 : 0.92 * easeOut((t - 0.5) / (T_HOLD - 0.5));
        bar.current.style.transform = `scaleX(${p})`;
      }
      if (wrap.current) {
        wrap.current.style.setProperty("--ui", String(clamp01((t - 1.0) / 0.7) * (1 - clamp01(ex * 3))));
        wrap.current.style.opacity = String(1 - clamp01((ex - 0.5) / 0.5));
      }

      if (ex >= 1) { if (!finished) { finished = true; setGone(true); onDone(); } return; }
      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (gone) return null;
  return (
    <div className="intro" ref={wrap} role="status" aria-label="Loading BolBazaar">
      <canvas ref={cv} className="intro-canvas" />
      <div className="intro-ui">
        <div className="intro-track"><span ref={bar} /></div>
      </div>
    </div>
  );
}
