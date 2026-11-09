import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { ffprobe } from "./media.js";

export interface FixtureInfo { path: string; seconds: number; sampleRate: number; channels: number }

export function fixture(name: string): FixtureInfo {
  const p = path.join(config.paths.fixtures, name);
  if (!fs.existsSync(p)) throw new Error(`Missing audio fixture ${p}`);
  const head = fs.readFileSync(p).subarray(0, 12).toString("latin1");
  if (!head.startsWith("RIFF") || !head.endsWith("WAVE")) throw new Error(`${name} is not a RIFF/WAVE file`);
  const pr = ffprobe(p);
  if (pr.duration < 1) throw new Error(`${name} is shorter than 1 second`);
  if (pr.duration > 28) throw new Error(`${name} is ${pr.duration.toFixed(1)}s; the speech API accepts at most ~28s per segment`);
  return { path: p, seconds: pr.duration, sampleRate: pr.sampleRate ?? 0, channels: pr.channels ?? 0 };
}
