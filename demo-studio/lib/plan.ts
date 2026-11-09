import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { SCENES } from "../config/scenes.js";
import { config } from "../config/demo.config.js";
import type { Plan, PlanScene, Seg, Sub, WaveSpec, Box } from "../remotion/types.js";
import { fixture } from "./fixtures.js";
import { ensureDir, readJson, writeJson } from "./log.js";
import { ffprobe } from "./media.js";
import type { SceneRecording } from "./session.js";
import type { VoiceManifest } from "../scripts/generate-voice.js";

const FPS = config.video.fps;
const LEAD = 0.45, GAP = 0.45;
const f = (s: number) => Math.round(s * FPS);

type Win = { rec: SceneRecording; from: number; to: number; mult?: number };

const mk = (pub: string) => path.posix.join("rec", pub);

/** Envelope (0..1) of a WAV, 30 values per second, used to draw the waveform of the audio the app really heard. */
function envelope(wavFile: string): number[] {
  const r = spawnSync("ffmpeg", ["-v", "error", "-i", wavFile, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], { maxBuffer: 1 << 26 });
  if (r.status !== 0) return [];
  const b = r.stdout, n = Math.floor(b.length / 2), win = Math.floor(8000 / FPS), out: number[] = [];
  for (let i = 0; i + win <= n; i += win) { let s = 0; for (let j = 0; j < win; j++) { const v = b.readInt16LE((i + j) * 2) / 32768; s += v * v; } out.push(Math.sqrt(s / win)); }
  const sorted = [...out].sort((a, c) => a - c), ref = sorted[Math.floor(sorted.length * 0.95)] || 1;
  return out.map((v) => Math.min(1, Math.sqrt(v / ref)) * 0.95 + 0.04);
}

function splitSubtitle(text: string): string[] {
  const parts = text.match(/[^.!?]+[.!?]*/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
  const out: string[] = [];
  for (const p of parts) {
    if (p.length <= 92) { out.push(p); continue; }
    const mid = p.indexOf(",", Math.floor(p.length * 0.3));
    if (mid > 0 && mid < p.length - 20) { out.push(p.slice(0, mid + 1).trim(), p.slice(mid + 1).trim()); } else out.push(p);
  }
  return out;
}

export function buildPlan(voice: VoiceManifest, recs: Record<string, SceneRecording>): { plan: Plan; stage: { from: string; to: string }[]; srt: string } {
  const stage: { from: string; to: string }[] = [];
  const stageFile = (from: string, to: string) => { if (!stage.some((s) => s.to === to)) stage.push({ from, to }); return to; };
  const order = recs["rep-order"], corr = recs["rep-correct-confirm"], mgr = recs["manager"];
  const m = (r: SceneRecording, k: string) => { const v = r.markers[k]; if (v == null) throw new Error(`recording ${r.name} has no marker "${k}"`); return v; };

  // The rep's own voice (the fixture fed to the app's microphone) is also made audible in the video. The "rep" scene is
  // therefore laid out as: [home -> mic tap] stretched to fit the narration, then [recording] at 1x so the voice is real-time.
  const repFx = fixture(config.fixtures.order);
  const repHome = Math.max(0, m(order, "home") - 0.1), repStart = m(order, "recording-start"), repStop = m(order, "recording-stop") + 0.3;
  const repSrcA = repStart - repHome, repSrcB = repStop - repStart;
  let repDAF = 0; // frames of the pre-recording part of the rep scene

  // ---- 1. durations ----
  const scenes: PlanScene[] = [];
  let cursorF = 0;
  const narration: Plan["narration"] = [];
  const srtRows: { a: number; b: number; text: string }[] = [];
  for (const def of SCENES) {
    const clips = voice.clips.filter((c) => c.sceneId === def.id);
    const lead = def.id === "intro" ? 1.7 : LEAD;
    const narrEnd = lead + clips.reduce((s, c) => s + c.duration, 0) + GAP * Math.max(0, clips.length - 1);
    let total = narrEnd + def.tail;
    if (def.id === "rep") {
      // the voice starts after the narration line; keep the slow-down of the pre-recording part within 0.5x..1.6x
      const dA = Math.min(repSrcA / 0.5, Math.max(repSrcA / 1.6, narrEnd + GAP));
      repDAF = f(dA);
      total = dA + repSrcB + def.tail + 0.4;
    }
    const durF = f(Math.max(def.minSeconds, total));
    const sc: PlanScene = { id: def.id, title: def.title, step: scenes.length + 1, startF: cursorF, durF, layout: "brand", segs: [], cursor: [], clicks: [], highlights: [], zooms: [], subs: [], kicker: "", headline: "", badges: [] };
    let t = lead;
    for (const c of clips) {
      const startLocal = f(t), dur = f(c.duration);
      const pubName = stageFile(c.file, path.posix.join("voice", path.basename(c.file)));
      narration.push({ src: pubName, startF: sc.startF + startLocal, durF: dur });
      const chunks = splitSubtitle(c.subtitle), chars = chunks.reduce((s, x) => s + x.length, 0);
      let a = startLocal;
      chunks.forEach((txt, i) => {
        const len = Math.max(f(1.2), Math.round((dur * txt.length) / chars));
        const to = i === chunks.length - 1 ? startLocal + dur + 8 : Math.min(a + len, sc.durF - 1);
        sc.subs.push({ text: txt, fromF: a, toF: Math.min(to, sc.durF - 1) } as Sub);
        srtRows.push({ a: (sc.startF + a) / FPS, b: (sc.startF + Math.min(to, sc.durF - 1)) / FPS, text: txt });
        a = to;
      });
      t += c.duration + GAP;
    }
    scenes.push(sc); cursorF += durF;
  }
  const S = Object.fromEntries(scenes.map((s) => [s.id, s])) as Record<string, PlanScene>;

  // ---- 2. recording windows -> segments ----
  const pubOf = (r: SceneRecording) => stageFile(r.file, mk(path.basename(r.file)));
  const fillSegs = (sc: PlanScene, wins: Win[], tailHold = 0.8) => {
    const avail = sc.durF / FPS - tailHold;
    const natural = wins.reduce((s, w) => s + (w.to - w.from) / (w.mult ?? 1), 0);
    const base = Math.min(1.8, Math.max(0.75, natural / avail));
    let at = 0;
    for (const w of wins) {
      const rate = base * (w.mult ?? 1), dur = Math.min((w.to - w.from) / rate, sc.durF / FPS - at);
      sc.segs.push({ src: pubOf(w.rec), srcFrom: w.from, rate, startF: f(at), durF: f(dur) } as Seg);
      at += dur;
    }
    const last = wins[wins.length - 1], remain = sc.durF - f(at);
    if (remain > 1) sc.segs.push({ src: pubOf(last.rec), srcFrom: last.to, rate: 1, startF: f(at), durF: remain, freeze: true });
    // make segments contiguous (rounding)
    for (let i = 1; i < sc.segs.length; i++) sc.segs[i].startF = sc.segs[i - 1].startF + sc.segs[i - 1].durF;
    const end = sc.segs[sc.segs.length - 1]; end.durF = sc.durF - end.startF;
  };
  const toF = (sc: PlanScene, rec: SceneRecording, srcT: number): number | null => {
    for (const s of sc.segs) {
      if (s.freeze || s.src !== mk(path.basename(rec.file))) continue;
      const end = s.srcFrom + (s.durF / FPS) * s.rate;
      if (srcT >= s.srcFrom - 1e-6 && srcT <= end + 1e-6) return s.startF + Math.round(((srcT - s.srcFrom) / s.rate) * FPS);
    }
    return null;
  };
  const cursorFrom = (sc: PlanScene, rec: SceneRecording) => {
    for (const e of rec.events) {
      const fr = toF(sc, rec, e.t); if (fr == null) continue;
      if (e.kind === "cursor" && e.x != null && e.y != null) sc.cursor.push({ f: fr, x: e.x, y: e.y });
      if (e.kind === "click" && e.x != null && e.y != null) sc.clicks.push({ f: fr, x: e.x, y: e.y });
    }
    sc.cursor.sort((a, b) => a.f - b.f);
  };
  const boxOf = (rec: SceneRecording, name: string): Box | undefined => rec.events.find((e) => e.kind === "box" && e.name === name)?.box;
  const boxTime = (rec: SceneRecording, name: string): number | undefined => rec.events.find((e) => e.kind === "box" && e.name === name)?.t;
  const center = (b: Box) => ({ cx: b.x + b.w / 2, cy: b.y + b.h / 2 });
  /** Highlight boxes shown one after another in even slots from frame `from`, each with a zoom-in. */
  const slots = (sc: PlanScene, rec: SceneRecording, items: [string, string][], from: number, to: number, zoom: number) => {
    const present = items.filter(([n]) => boxOf(rec, n));
    const slot = Math.floor((to - from) / Math.max(1, present.length));
    sc.zooms.push({ f: 0, scale: 1, cx: sc.viewport!.width / 2, cy: sc.viewport!.height / 2 });
    present.forEach(([n, label], i) => {
      const b = boxOf(rec, n)!, a = from + i * slot, e = a + slot;
      sc.highlights.push({ fromF: a, toF: e, box: b, label });
      const c = center(b);
      sc.zooms.push({ f: a + 6, scale: zoom, ...c }, { f: e - 6, scale: zoom, ...c });
    });
    const lastEnd = from + present.length * slot;
    sc.zooms.push({ f: Math.min(sc.durF - 1, lastEnd + 10), scale: 1, cx: sc.viewport!.width / 2, cy: sc.viewport!.height / 2 });
  };

  const phone = config.browser.phone, desk = config.browser.desktop;

  // scene: rep
  {
    const sc = S.rep; sc.layout = "phone"; sc.viewport = phone;
    sc.kicker = "The rep"; sc.headline = "Speak the visit."; sc.body = "One tap on the mic. The rep talks the way they always do, in Hinglish.";
    const bF = Math.min(f(repSrcB), sc.durF - repDAF);
    sc.segs.push({ src: pubOf(order), srcFrom: repHome, rate: repSrcA / (repDAF / FPS), startF: 0, durF: repDAF } as Seg);
    sc.segs.push({ src: pubOf(order), srcFrom: repStart, rate: 1, startF: repDAF, durF: bF } as Seg);
    if (sc.durF - repDAF - bF > 1) sc.segs.push({ src: pubOf(order), srcFrom: repStop, rate: 1, startF: repDAF + bF, durF: sc.durF - repDAF - bF, freeze: true } as Seg);
    cursorFrom(sc, order);
    const fx = repFx;
    // make the rep's voice audible exactly while the recorder is live (the fake microphone starts with the stream)
    narration.push({ src: stageFile(fx.path, "voice/rep-voice.wav"), startF: sc.startF + repDAF + f(0.15), durF: f(fx.seconds) });
    const samples = envelope(fx.path);
    sc.wave = { samples, perSec: FPS, recStartSrc: m(order, "recording-start") + 0.15, recEndSrc: m(order, "recording-stop"), src: "" } as WaveSpec;
    const mic = boxOf(order, "mic"), rs = toF(sc, order, m(order, "recording-start"));
    if (mic && rs != null) { sc.highlights.push({ fromF: rs + 4, toF: Math.min(sc.durF - 4, rs + 4 + f(3.5)), box: mic, label: "Microphone" }); }
  }

  // scene: extraction
  {
    const sc = S.extraction; sc.layout = "phone"; sc.viewport = phone;
    sc.kicker = "Understood"; sc.headline = "Visit to structured data."; sc.body = "Everything the rep said, in the app's own fields. Nothing is saved until they confirm.";
    const stopT = m(order, "recording-stop") + 0.3, verT = m(order, "verified");
    const hasClar = corr.markers["clarification"] != null;
    fillSegs(sc, [
      { rec: order, from: stopT, to: verT + 0.1, mult: 0.8 },
      ...(hasClar ? [{ rec: corr, from: 0.3, to: m(corr, "review") + 0.2 } as Win] : []),
    ], 0.5);
    cursorFrom(sc, order); if (hasClar) cursorFrom(sc, corr);
    const firstEnd = sc.segs[0].durF;
    const labels: [string, string][] = [["retailer", "Retailer"], ["order", "Order"], ["payment", "Payment"], ["followups", "Follow-ups"], ["complaint", "Complaint"]];
    slots(sc, order, labels, 8, firstEnd - 4, 1.4);
    sc.chips = labels.filter(([n]) => boxOf(order, n)).map(([, l]) => l);
    if (hasClar) {
      const cb = boxOf(corr, "clarification"), ct = boxTime(corr, "clarification"), cf = ct != null ? toF(sc, corr, ct) : null;
      if (cb && cf != null) {
        sc.highlights.push({ fromF: cf, toF: cf + f(3), box: cb, label: "Clarification" });
        sc.badges.push({ fromF: cf, toF: sc.durF - 6, text: "Unsure which product? It asks instead of guessing." });
        const c = center(cb); sc.zooms.push({ f: cf - 6, scale: 1, cx: phone.width / 2, cy: phone.height / 2 }, { f: cf + 8, scale: 1.3, ...c }, { f: cf + f(3), scale: 1, cx: phone.width / 2, cy: phone.height / 2 });
      }
    }
    sc.zooms.sort((a, b) => a.f - b.f);
  }

  // scene: correction
  {
    const sc = S.correction; sc.layout = "phone"; sc.viewport = phone;
    const voiceMode = corr.facts.correctionMode === "voice";
    sc.kicker = "Correct it"; sc.headline = voiceMode ? "Say the fix." : "Fix it in one line."; sc.body = "No re-recording. The server applies the change and recomputes every total.";
    const t0 = m(corr, "review") - 0.2, t1 = m(corr, "corrected") + 2.6;
    fillSegs(sc, [{ rec: corr, from: t0, to: t1 }], 0.5);
    cursorFrom(sc, corr);
    const cf = toF(sc, corr, m(corr, "corrected")) ?? Math.floor(sc.durF / 2);
    const lab: [string, string][] = [["corrected-item", "Updated quantity"], ["total", "Recalculated total"]];
    const present = lab.filter(([n]) => boxOf(corr, n));
    const slot = Math.max(f(1.4), Math.floor((sc.durF - 8 - (cf + 6)) / Math.max(1, present.length)));
    sc.zooms.push({ f: 0, scale: 1, cx: phone.width / 2, cy: phone.height / 2 });
    present.forEach(([n, label], i) => {
      const b = boxOf(corr, n)!, a = cf + 6 + i * slot;
      sc.highlights.push({ fromF: a, toF: a + slot, box: b, label });
      const c = center(b); sc.zooms.push({ f: a + 6, scale: 1.4, ...c }, { f: a + slot - 6, scale: 1.4, ...c });
    });
    sc.zooms.push({ f: Math.min(sc.durF - 1, cf + 6 + present.length * slot + 8), scale: 1, cx: phone.width / 2, cy: phone.height / 2 });
    sc.zooms.sort((a, b) => a.f - b.f);
    sc.chips = ["Correction", ...present.map(([, l]) => l)];
    sc.highlights.push({ fromF: Math.max(0, (toF(sc, corr, m(corr, "correction-start")) ?? 0)), toF: Math.max(0, (toF(sc, corr, m(corr, "correction-start")) ?? 0)) + f(2), box: boxOf(corr, "notice") ?? { x: 0, y: 0, w: 0, h: 0 }, label: "Correction" });
    sc.highlights = sc.highlights.filter((h) => h.box.w > 0);
    const fa = corr.facts as { totalBefore?: number; totalAfter?: number };
    if (fa.totalBefore && fa.totalAfter) sc.badges.push({ fromF: cf, toF: sc.durF - 6, text: `Total  ₹${fa.totalBefore.toLocaleString("en-IN")}  →  ₹${fa.totalAfter.toLocaleString("en-IN")}` });
  }

  // scene: confirmation
  {
    const sc = S.confirmation; sc.layout = "phone"; sc.viewport = phone;
    sc.kicker = "Confirmed"; sc.headline = "The rep decides."; sc.body = "AI proposes. The rep verifies. The app commits only after Confirm.";
    const t0 = m(corr, "corrected") + 2.6, t1 = m(corr, "persisted") - 0.4;
    fillSegs(sc, [{ rec: corr, from: t0, to: t1 }], 0.6);
    cursorFrom(sc, corr);
    sc.zooms.push({ f: 0, scale: 1, cx: phone.width / 2, cy: phone.height / 2 });
    const cb = boxOf(corr, "confirm-button"), sb = boxOf(corr, "saved-stats");
    const savedF = toF(sc, corr, m(corr, "saved")) ?? Math.floor(sc.durF * 0.6);
    if (cb) { const c = center(cb); sc.highlights.push({ fromF: 4, toF: Math.max(20, (toF(sc, corr, m(corr, "confirm-clicked")) ?? 60) + 6), box: cb, label: "Confirm" }); sc.zooms.push({ f: 14, scale: 1.25, ...c }, { f: Math.max(30, savedF - 4), scale: 1.25, ...c }); }
    if (sb) { const c = center(sb); sc.highlights.push({ fromF: savedF + 6, toF: Math.min(sc.durF - 4, savedF + 6 + f(3)), box: sb, label: "Saved" }); sc.zooms.push({ f: savedF + 10, scale: 1.3, ...c }, { f: Math.min(sc.durF - 2, savedF + f(3)), scale: 1.3, ...c }); }
    sc.zooms.sort((a, b) => a.f - b.f);
    sc.chips = ["Review", "Confirm", "Saved"];
    const quote = String(corr.facts.confirmationText ?? "").replace(/[“”"]/g, "").trim();
    if (quote) sc.badges.push({ fromF: savedF + 4, toF: sc.durF - 6, text: `App reply: “${quote.length > 96 ? quote.slice(0, 93) + "…" : quote}”` });
    // spoken reply from the app, only when it is real speech (live TTS), not the offline chirp
    const replyFile = corr.facts.replyAudio as string | undefined;
    if (replyFile && fs.existsSync(replyFile) && ffprobe(replyFile).duration > 1.5) {
      const dur = ffprobe(replyFile).duration;
      narration.push({ src: stageFile(replyFile, "voice/app-reply.wav"), startF: sc.startF + savedF + 8, durF: f(dur) });
    }
  }

  // scene: manager
  {
    const sc = S.manager; sc.layout = "desktop"; sc.viewport = desk;
    sc.kicker = "Real-time visibility";
    const t0 = Math.max(0, m(mgr, "dashboard") - 0.2), t1 = m(mgr, "answered") + 3.5;
    fillSegs(sc, [{ rec: mgr, from: t0, to: t1 }], 0.6);
    cursorFrom(sc, mgr);
    sc.zooms.push({ f: 0, scale: 1, cx: desk.width / 2, cy: desk.height / 2 });
    const pb = boxOf(mgr, "panels"), pt = boxTime(mgr, "panels"), ab = boxOf(mgr, "answer"), at = boxTime(mgr, "answer");
    const pf = pt != null ? toF(sc, mgr, pt) : null, af = at != null ? toF(sc, mgr, at) : null;
    if (pb && pf != null) { sc.highlights.push({ fromF: pf, toF: pf + f(3), box: pb, label: "Overdue payments" }); const c = center(pb); sc.zooms.push({ f: pf + 8, scale: 1.5, ...c }, { f: pf + f(3), scale: 1.5, ...c }, { f: pf + f(3.6), scale: 1, cx: desk.width / 2, cy: desk.height / 2 }); }
    if (ab && af != null) { sc.highlights.push({ fromF: af, toF: Math.min(sc.durF - 4, af + f(4)), box: ab, label: "Answer" }); const c = center(ab); sc.zooms.push({ f: af - 4, scale: 1, cx: desk.width / 2, cy: desk.height / 2 }, { f: af + 10, scale: 1.6, ...c }, { f: Math.min(sc.durF - 2, af + f(4)), scale: 1.6, ...c }); }
    sc.zooms.sort((a, b) => a.f - b.f);
  }

  // brand scenes
  S.intro.layout = "brand"; S.outro.layout = "brand";

  const total = cursorF;
  // ---- 3. sound design ----
  const sfx: Plan["sfx"] = [
    { src: stageFile(path.join(config.paths.music, "sfx-hit.wav"), "audio/sfx-hit.wav"), startF: 4, volume: 0.5 },
    ...scenes.slice(1).map((s) => ({ src: stageFile(path.join(config.paths.music, "sfx-whoosh.wav"), "audio/sfx-whoosh.wav"), startF: s.startF - 12, volume: 0.28 })),
    { src: stageFile(path.join(config.paths.music, "sfx-chime.wav"), "audio/sfx-chime.wav"), startF: S.outro.startF + 26, volume: 0.35 },
  ];
  // a small "pop" on every real click the cursor makes (at least 0.5 s apart)
  let lastPop = -999;
  for (const sc of scenes) for (const c of [...sc.clicks].sort((a, b) => a.f - b.f)) {
    const g = sc.startF + c.f; if (g - lastPop < 15) continue; lastPop = g;
    sfx.push({ src: stageFile(path.join(config.paths.music, "sfx-pop.wav"), "audio/sfx-pop.wav"), startF: g, volume: 0.3 });
  }
  const music = stageFile(path.join(config.paths.music, "music-bed.wav"), "audio/music-bed.wav");

  const srt = srtRows.map((r, i) => `${i + 1}\n${ts(r.a)} --> ${ts(r.b)}\n${r.text}\n`).join("\n");
  const plan: Plan = { fps: FPS, width: config.video.width, height: config.video.height, totalF: total, scenes, narration, music, sfx, websiteUrl: config.video.websiteUrl || undefined };
  return { plan, stage, srt };
}

const ts = (s: number) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60), ms = Math.round((s % 1) * 1000); const p = (n: number, w = 2) => String(n).padStart(w, "0"); return `${p(h)}:${p(m)}:${p(sec)},${p(ms, 3)}`; };

export function loadRecordings(): Record<string, SceneRecording> {
  const out: Record<string, SceneRecording> = {};
  for (const n of ["rep-order", "rep-correct-confirm", "manager"]) {
    const p = path.join(config.paths.sceneRecordings, `${n}.json`);
    if (!fs.existsSync(p)) throw new Error(`Missing scene recording ${n}. Run npm run demo:record first.`);
    out[n] = readJson<SceneRecording>(p);
  }
  return out;
}

export function writePlanFiles(plan: Plan, srt: string) {
  ensureDir(config.paths.subtitles);
  writeJson(path.join(config.paths.runtime, "plan.json"), plan);
  fs.writeFileSync(path.join(config.paths.subtitles, "bolbazaar-demo.srt"), srt);
}
