import { spawnSync } from "node:child_process";
import fs from "node:fs";

export interface Probe { duration: number; width?: number; height?: number; fps?: number; hasAudio: boolean; hasVideo: boolean; videoCodec?: string; audioCodec?: string; sampleRate?: number; channels?: number; format?: string }

export function ffprobe(file: string): Probe {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_format", "-show_streams", "-of", "json", file], { encoding: "utf8", maxBuffer: 1 << 26 });
  if (r.status !== 0) throw new Error(`ffprobe failed for ${file}: ${r.stderr}`);
  const j = JSON.parse(r.stdout);
  const v = j.streams.find((s: any) => s.codec_type === "video");
  const a = j.streams.find((s: any) => s.codec_type === "audio");
  const [n, d] = String(v?.avg_frame_rate ?? "0/1").split("/").map(Number);
  return {
    duration: Number(j.format?.duration ?? v?.duration ?? a?.duration ?? 0),
    width: v?.width, height: v?.height, fps: d ? n / d : undefined,
    hasAudio: !!a, hasVideo: !!v, videoCodec: v?.codec_name, audioCodec: a?.codec_name,
    sampleRate: a ? Number(a.sample_rate) : undefined, channels: a?.channels, format: j.format?.format_name,
  };
}

export function ffmpeg(args: string[]) {
  const r = spawnSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", ...args], { encoding: "utf8" });
  if (r.status !== 0) throw new Error(`ffmpeg ${args.join(" ")} failed: ${r.stderr}`);
}

export const exists = (f: string) => { try { return fs.statSync(f).size > 0; } catch { return false; } };

/** Mean brightness/variance sample of a frame (0-255) to detect blank scenes. */
export function frameStats(file: string, atSeconds: number): { mean: number; std: number } {
  const r = spawnSync("ffmpeg", ["-v", "error", "-ss", String(atSeconds), "-i", file, "-frames:v", "1", "-vf", "scale=96:-1,format=gray", "-f", "rawvideo", "-"], { maxBuffer: 1 << 24 });
  if (r.status !== 0 || !r.stdout.length) throw new Error(`could not sample ${file}@${atSeconds}`);
  const px = r.stdout; let sum = 0; for (const p of px) sum += p;
  const mean = sum / px.length; let v = 0; for (const p of px) v += (p - mean) ** 2;
  return { mean, std: Math.sqrt(v / px.length) };
}
