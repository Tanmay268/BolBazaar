import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { ensureDir, log } from "../lib/log.js";
import { ensureAudioAssets } from "../lib/synth.js";
import { ffmpeg } from "../lib/media.js";
import { buildPlan, loadRecordings, writePlanFiles } from "../lib/plan.js";
import { loadManifest } from "./generate-voice.js";

const PUBLIC = path.join(config.paths.root, "public");
export const FINAL = path.join(config.paths.artifacts, "bolbazaar-demo.mp4");

export async function renderDemo(opts: { stills?: number[] } = {}) {
  ensureAudioAssets();
  const voice = loadManifest();
  const recs = loadRecordings();
  const { plan, stage, srt } = buildPlan(voice, recs);
  writePlanFiles(plan, srt);

  // stage every file the composition references into Remotion's public dir
  fs.rmSync(PUBLIC, { recursive: true, force: true });
  for (const s of stage) { const dest = path.join(PUBLIC, s.to); ensureDir(path.dirname(dest)); fs.copyFileSync(s.from, dest); }
  log.info(`Plan: ${plan.scenes.length} scenes, ${(plan.totalF / plan.fps).toFixed(1)}s, ${plan.narration.length} narration clips`);

  const serveUrl = await bundle({ entryPoint: path.join(config.paths.root, "remotion", "index.ts"), publicDir: PUBLIC, onProgress: () => undefined });
  const composition = await selectComposition({ serveUrl, id: "BolBazaarDemo", inputProps: { plan } });
  ensureDir(config.paths.artifacts);

  if (opts.stills?.length) {
    const dir = ensureDir(path.join(config.paths.artifacts, "stills"));
    for (const fr of opts.stills) await renderStill({ composition, serveUrl, frame: Math.min(fr, plan.totalF - 1), output: path.join(dir, `frame-${String(fr).padStart(4, "0")}.png`), inputProps: { plan } });
    log.ok(`Rendered ${opts.stills.length} stills to ${dir}`);
    return null;
  }

  const raw = path.join(config.paths.runtime, "remotion-out.mp4");
  let lastPct = -1;
  await renderMedia({
    composition, serveUrl, codec: "h264", outputLocation: raw, inputProps: { plan },
    crf: 16, pixelFormat: "yuv420p", audioCodec: "aac", audioBitrate: "192k", concurrency: Math.max(2, Math.floor(os.cpus().length / 2)),
    onProgress: ({ progress }) => { const p = Math.floor(progress * 10) * 10; if (p !== lastPct) { lastPct = p; log.info(`render ${p}%`); } },
  });

  // Final audio pass with FFmpeg: loudness-normalise (-16 LUFS, true peak -1.5 dB) so narration is clearly audible and nothing clips.
  ffmpeg(["-i", raw, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", FINAL]);
  log.ok(`Final video: ${FINAL}`);
  return { plan, final: FINAL };
}


if (process.argv[1]?.endsWith("generate-video.ts")) {
  const stills = process.argv.filter((a) => a.startsWith("--still=")).flatMap((a) => a.slice(8).split(",").map(Number));
  renderDemo({ stills }).catch((e) => { log.fail(String(e.stack ?? e)); process.exit(1); });
}
