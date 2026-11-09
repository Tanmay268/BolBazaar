import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { ensureDir } from "./log.js";

/**
 * Original, copyright-free audio generated from scratch (sine/triangle synthesis): an ambient music bed and a few
 * transition sounds. Nothing here is sampled from third-party material.
 */
const RATE = 44100;

function wav(left: Float32Array, right: Float32Array): Buffer {
  const n = left.length, buf = Buffer.alloc(44 + n * 4);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write("WAVEfmt ", 8); buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22); buf.writeUInt32LE(RATE, 24); buf.writeUInt32LE(RATE * 4, 28);
  buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write("data", 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, left[i])) * 32767), 44 + i * 4);
    buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, right[i])) * 32767), 46 + i * 4);
  }
  return buf;
}

const hz = (midi: number) => 440 * 2 ** ((midi - 69) / 12);
const norm = (l: Float32Array, r: Float32Array, peak: number) => {
  let m = 0; for (let i = 0; i < l.length; i++) m = Math.max(m, Math.abs(l[i]), Math.abs(r[i]));
  const g = m ? peak / m : 1; for (let i = 0; i < l.length; i++) { l[i] *= g; r[i] *= g; }
};

export function makeMusic(seconds = 96): Buffer {
  // Upbeat bed: 116 bpm, C - G - Am - F, sidechain-pumped pad, kick/clap/hat groove, bouncy bass, sparkling 16th arpeggio.
  const n = seconds * RATE, L = new Float32Array(n), R = new Float32Array(n);
  const bpm = 116, beat = 60 / bpm, bar = beat * 4, s16 = beat / 4;
  const chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]];
  let seed = 12345, lpC = 0;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed / 2147483647) * 2 - 1; };
  const bassPat = [0, -1, 0, 0, -1, 0, 7, -1, 0, -1, 0, 0, -1, 7, 0, -1]; // semitone offsets from the chord root, -1 = rest
  const arpPat = [0, 1, 2, 1, 2, 1, 2, 3, 2, 1, 2, 1, 0, 1, 2, 4];
  for (let i = 0; i < n; i++) {
    const t = i / RATE, bi = Math.floor(t / bar), ch = chords[bi % chords.length];
    const tb = t - Math.floor(t / beat) * beat, beatNo = Math.floor(t / beat) % 4;
    const k16 = Math.floor(t / s16), t16 = t - k16 * s16, st = k16 % 16;
    const intro = Math.min(1, 0.45 + t / (bar * 3)); // groove builds up over the first bars
    // pad, ducked on every beat (sidechain feel)
    let pad = 0;
    for (const m of ch) { const f = hz(m); pad += Math.sin(2 * Math.PI * f * t) * 0.5 + Math.sin(2 * Math.PI * f * 2.003 * t) * 0.12 + Math.sin(2 * Math.PI * f * 0.998 * t) * 0.3; }
    pad *= 0.1 * (1 - 0.55 * Math.exp(-tb * 9));
    // bouncy bass
    const bo = bassPat[st];
    const bass = bo < 0 ? 0 : Math.sin(2 * Math.PI * hz(ch[0] - 24 + bo) * t) * Math.exp(-t16 * 7) * 0.3;
    // 16th arpeggio, accented on the beat
    const an = ch[arpPat[st] % 3] + 12 * (1 + (arpPat[st] > 2 ? 1 : 0));
    const arp = Math.sin(2 * Math.PI * hz(an) * t) * Math.exp(-t16 * 16) * (st % 4 === 0 ? 0.13 : 0.08);
    // drums
    const kick = (beatNo === 0 || beatNo === 2 || (beatNo === 3 && st % 16 === 14)) ? Math.sin(2 * Math.PI * (48 + 110 * Math.exp(-tb * 38)) * tb) * Math.exp(-tb * 8) * 0.55 : 0;
    const nz = rnd(); lpC += 0.35 * (nz - lpC);
    const clap = (beatNo === 1 || beatNo === 3) ? (nz - lpC) * Math.exp(-tb * 22) * 0.28 : 0;
    const hat = (nz - lpC) * Math.exp(-(t - Math.floor(t / (beat / 2)) * (beat / 2)) * 70) * ((Math.floor(t / (beat / 2)) % 2) ? 0.2 : 0.1);
    const drums = (kick + clap + hat) * intro;
    const sp = 0.5 + 0.5 * Math.sin(k16 * 0.7);
    L[i] = pad + bass + arp * (1 - 0.4 * sp) + drums;
    R[i] = pad * 0.97 + bass + arp * (0.6 + 0.4 * sp) + drums;
  }
  norm(L, R, 0.9);
  return wav(L, R);
}

export function makePop(): Buffer {
  const n = Math.floor(RATE * 0.16), L = new Float32Array(n), R = new Float32Array(n);
  for (let i = 0; i < n; i++) { const t = i / RATE; L[i] = R[i] = Math.sin(2 * Math.PI * (700 + 900 * Math.exp(-t * 40)) * t) * Math.exp(-t * 28); }
  norm(L, R, 0.8);
  return wav(L, R);
}

export function makeWhoosh(): Buffer {
  const n = Math.floor(RATE * 0.9), L = new Float32Array(n), R = new Float32Array(n);
  let lp = 0, seed = 7;
  for (let i = 0; i < n; i++) {
    const t = i / n, env = Math.sin(Math.PI * t) ** 2;
    seed = (seed * 16807) % 2147483647; const nz = (seed / 2147483647) * 2 - 1;
    const a = 0.02 + 0.5 * t * t; lp += a * (nz - lp);
    L[i] = lp * env; R[i] = lp * env * (0.9 + 0.1 * Math.sin(i / 900));
  }
  norm(L, R, 0.7);
  return wav(L, R);
}

export function makeHit(): Buffer {
  const n = Math.floor(RATE * 1.6), L = new Float32Array(n), R = new Float32Array(n);
  for (let i = 0; i < n; i++) { const t = i / RATE, v = Math.sin(2 * Math.PI * (55 + 40 * Math.exp(-t * 6)) * t) * Math.exp(-t * 2.4); L[i] = R[i] = v; }
  norm(L, R, 0.85);
  return wav(L, R);
}

export function makeChime(): Buffer {
  const n = Math.floor(RATE * 2.4), L = new Float32Array(n), R = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / RATE; let v = 0;
    for (const [m, d] of [[76, 0], [79, 0.12], [83, 0.24]] as const) if (t > d) v += Math.sin(2 * Math.PI * hz(m) * (t - d)) * Math.exp(-(t - d) * 2.2) * 0.4;
    L[i] = R[i] = v;
  }
  norm(L, R, 0.7);
  return wav(L, R);
}

export function ensureAudioAssets() {
  const dir = ensureDir(config.paths.music);
  const files: Record<string, () => Buffer> = { "music-bed.wav": () => makeMusic(), "sfx-whoosh.wav": makeWhoosh, "sfx-hit.wav": makeHit, "sfx-chime.wav": makeChime, "sfx-pop.wav": makePop };
  for (const [name, make] of Object.entries(files)) {
    const p = path.join(dir, name);
    if (!fs.existsSync(p)) fs.writeFileSync(p, make());
  }
  return dir;
}
