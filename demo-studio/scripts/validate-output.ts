import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { SCENES } from "../config/scenes.js";
import { config } from "../config/demo.config.js";
import { log, readJson, writeJson } from "../lib/log.js";
import { exists, ffprobe, frameStats } from "../lib/media.js";
import type { Plan } from "../remotion/types.js";
import type { RunReportScene } from "./record-demo.js";
import type { VoiceManifest } from "./generate-voice.js";

export interface ValidationCheck { name: string; ok: boolean; detail: string }
export interface SceneReport { scene: string; execution: string; recordedSeconds: number | null; finalSeconds: number | null; validation: "passed" | "failed"; failures: string[] }
export interface DemoReport {
  generatedAt: string; ok: boolean; output: string; durationSeconds: number | null; providers: string; correctionMode: string;
  checks: ValidationCheck[]; scenes: SceneReport[]; recordingScenes: RunReportScene[]; notes: string[];
}

const FINAL = path.join(config.paths.artifacts, "bolbazaar-demo.mp4");
const rt = (n: string) => path.join(config.paths.runtime, n);
const tryJson = <T>(p: string): T | null => { try { return readJson<T>(p); } catch { return null; } };

export function validate(): DemoReport {
  const checks: ValidationCheck[] = [];
  const add = (name: string, ok: boolean, detail = "") => checks.push({ name, ok, detail });
  const plan = tryJson<Plan>(rt("plan.json"));
  const voice = tryJson<VoiceManifest>(path.join(config.paths.voice, "manifest.json"));
  const rec = tryJson<RunReportScene[]>(rt("record-report.json")) ?? [];
  const pre = tryJson<{ providers: string; correctionMode: string }>(rt("preflight.json"));

  // 1. scene recordings
  const recNames = ["rep-order", "rep-correct-confirm", "manager"];
  const recProbe: Record<string, number> = {};
  for (const n of recNames) {
    const f = path.join(config.paths.sceneRecordings, `${n}.mp4`);
    const ok = exists(f); if (ok) recProbe[n] = ffprobe(f).duration;
    add(`scene recording ${n}`, ok, ok ? `${recProbe[n].toFixed(1)}s` : "missing");
  }
  // 2. audio clips
  const clipsOk = !!voice && SCENES.every((s) => voice.clips.some((c) => c.sceneId === s.id && exists(c.file)));
  add("narration clip for every scene", clipsOk, voice ? `${voice.clips.length} clips (${voice.provider})` : "no voice manifest");
  // 3. subtitles
  const srt = path.join(config.paths.subtitles, "bolbazaar-demo.srt");
  const srtCount = exists(srt) ? (fs.readFileSync(srt, "utf8").match(/-->/g) ?? []).length : 0;
  add("subtitles generated", !!voice && srtCount >= voice.clips.length, `${srtCount} cues`);
  // 4. final video
  const there = exists(FINAL);
  add("final video exists", there, FINAL);
  let probe: ReturnType<typeof ffprobe> | null = null;
  if (there) {
    try { probe = ffprobe(FINAL); } catch (e: any) { add("valid MP4 (ffprobe)", false, e.message); }
  }
  if (probe) {
    add("valid MP4 container", /mp4/.test(probe.format ?? "") && probe.videoCodec === "h264" && probe.audioCodec === "aac", `${probe.format}, ${probe.videoCodec}/${probe.audioCodec}`);
    add("resolution 1920x1080", probe.width === config.video.width && probe.height === config.video.height, `${probe.width}x${probe.height}`);
    add("30 FPS", Math.abs((probe.fps ?? 0) - config.video.fps) < 0.01, `${probe.fps?.toFixed(2)}`);
    add(`duration ${config.video.minSeconds}-${config.video.maxSeconds}s`, probe.duration >= config.video.minSeconds && probe.duration <= config.video.maxSeconds, `${probe.duration.toFixed(1)}s`);
    add("audio present", probe.hasAudio, `${probe.sampleRate} Hz, ${probe.channels} ch`);
    // audio level: must not be silent and must not clip
    const vol = spawnSync("ffmpeg", ["-hide_banner", "-i", FINAL, "-af", "volumedetect", "-vn", "-f", "null", "-"], { encoding: "utf8" }).stderr;
    const mean = Number(/mean_volume: (-?[\d.]+) dB/.exec(vol)?.[1] ?? NaN), peak = Number(/max_volume: (-?[\d.]+) dB/.exec(vol)?.[1] ?? NaN);
    add("audio audible and not clipping", mean > -32 && peak <= -0.5, `mean ${mean} dB, peak ${peak} dB`);
    // sync: audio stream vs video stream length
    const a = spawnSync("ffprobe", ["-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "csv=p=0", FINAL], { encoding: "utf8" }).stdout;
    const v = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", FINAL], { encoding: "utf8" }).stdout;
    const drift = Math.abs(parseFloat(a) - parseFloat(v));
    add("audio/video durations synchronised (<0.3s)", drift < 0.3, `drift ${drift.toFixed(3)}s`);
    if (plan) add("duration matches plan", Math.abs(probe.duration - plan.totalF / plan.fps) < 0.5, `plan ${(plan.totalF / plan.fps).toFixed(1)}s`);
    // playable: decode everything, any error fails
    const dec = spawnSync("ffmpeg", ["-v", "error", "-i", FINAL, "-f", "null", "-"], { encoding: "utf8" });
    add("playable (full decode, no errors)", dec.status === 0 && !dec.stderr.trim(), dec.stderr.trim().slice(0, 200) || "clean");
  }
  // 12. browser errors during the workflow
  const failedRec = rec.filter((r) => r.status !== "passed");
  add("no browser/interaction error interrupted the workflow", rec.length === recNames.length && failedRec.length === 0, failedRec.map((f) => `${f.name}: ${f.error}`).join("; ") || `${rec.length} scenes passed`);
  const recErrors = recNames.flatMap((n) => tryJson<{ errors: string[] }>(path.join(config.paths.sceneRecordings, `${n}.json`))?.errors ?? []);
  add("no console/page/HTTP 5xx errors in recordings", recErrors.length === 0, recErrors.slice(0, 2).join("; ") || "none");

  // per-scene report + 11. blank-scene detection
  const scenes: SceneReport[] = [];
  for (const def of SCENES) {
    const ps = plan?.scenes.find((s) => s.id === def.id);
    const failures: string[] = [];
    const recName = ({ rep: "rep-order", extraction: "rep-order", correction: "rep-correct-confirm", confirmation: "rep-correct-confirm", manager: "manager" } as Record<string, string>)[def.id];
    if (!voice?.clips.some((c) => c.sceneId === def.id && exists(c.file))) failures.push("narration clip missing");
    if (recName && !(recName in recProbe)) failures.push(`recording ${recName} missing`);
    if (recName) { const r = rec.find((x) => x.name === recName); if (!r || r.status !== "passed") failures.push(`recording ${recName}: ${r?.error ?? "not executed"}`); }
    let finalSeconds: number | null = null;
    if (ps && probe) {
      finalSeconds = ps.durF / config.video.fps;
      for (const at of [0.35, 0.65]) {
        try {
          const st = frameStats(FINAL, (ps.startF + ps.durF * at) / config.video.fps);
          if (st.std < 6) failures.push(`frame at ${(at * 100).toFixed(0)}% looks blank (std ${st.std.toFixed(1)})`);
        } catch (e: any) { failures.push(e.message); }
      }
    } else failures.push("scene not in final video");
    scenes.push({ scene: def.id, execution: recName ? (rec.find((x) => x.name === recName)?.status ?? "not run") : "rendered (brand scene)", recordedSeconds: recName ? recProbe[recName] ?? null : null, finalSeconds, validation: failures.length ? "failed" : "passed", failures });
  }
  add("no scene is blank", scenes.every((s) => !s.failures.some((f) => f.includes("blank"))), "sampled 2 frames per scene");

  const notes: string[] = [];
  if (pre?.providers && /speech=offline|reasoner=offline/.test(pre.providers)) notes.push("Recorded against OFFLINE providers: the speech-to-text step is the app's deterministic stub (it ignores the audio content) and extraction is rule-based. The audio pipeline (microphone, WAV encoding, upload) is real; the transcript is not derived from the fixture. Re-run with DEMO_PROVIDER_MODE=live for genuine Gnani/Azure results.");
  if (pre?.correctionMode === "typed") notes.push("The correction was applied through the app's real typed-correction field, because spoken correction needs live speech-to-text and a correction.wav fixture.");
  const ok = checks.every((c) => c.ok) && scenes.every((s) => s.validation === "passed");
  return { generatedAt: new Date().toISOString(), ok, output: FINAL, durationSeconds: probe?.duration ?? null, providers: pre?.providers ?? "unknown", correctionMode: pre?.correctionMode ?? "unknown", checks, scenes, recordingScenes: rec, notes };
}

export function writeReports(r: DemoReport) {
  writeJson(path.join(config.paths.artifacts, "demo-report.json"), r);
  const md = [
    `# BolBazaar demo report`, ``,
    `- **Result:** ${r.ok ? "PASSED" : "FAILED"}`, `- **Video:** \`${path.relative(config.paths.repo, r.output)}\` (${r.durationSeconds?.toFixed(1) ?? "n/a"}s)`,
    `- **Providers:** ${r.providers} · **Correction:** ${r.correctionMode}`, `- **Generated:** ${r.generatedAt}`, ``,
    `## Scenes`, ``, `| Scene | Execution | Recorded | In video | Validation | Failure details |`, `|---|---|---|---|---|---|`,
    ...r.scenes.map((s) => `| ${s.scene} | ${s.execution} | ${s.recordedSeconds?.toFixed(1) ?? "-"}s | ${s.finalSeconds?.toFixed(1) ?? "-"}s | ${s.validation} | ${s.failures.join("; ") || "-"} |`), ``,
    `## Checks`, ``, ...r.checks.map((c) => `- ${c.ok ? "✅" : "❌"} **${c.name}** — ${c.detail}`), ``,
    ...(r.notes.length ? [`## Notes`, ``, ...r.notes.map((n) => `- ${n}`), ``] : []),
    `## Verified application facts`, ``, "```json", JSON.stringify(Object.fromEntries(r.recordingScenes.map((s) => [s.name, s.facts])), null, 2), "```", ``,
  ].join("\n");
  fs.writeFileSync(path.join(config.paths.artifacts, "demo-report.md"), md);
}

if (process.argv[1]?.endsWith("validate-output.ts")) {
  const r = validate(); writeReports(r);
  for (const c of r.checks) (c.ok ? log.ok : log.fail)(`${c.name}: ${c.detail}`);
  for (const s of r.scenes) (s.validation === "passed" ? log.ok : log.fail)(`scene ${s.scene}: ${s.validation} ${s.failures.join("; ")}`);
  process.exit(r.ok ? 0 : 1);
}
