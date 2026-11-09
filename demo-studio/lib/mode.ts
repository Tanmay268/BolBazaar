import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";

/**
 * How the correction is performed.
 *  voice: correction.wav goes through the real microphone path -> speech-to-text -> patch (needs live speech).
 *  typed: the offline speech stub ignores audio content, so the real "type a correction" field is used instead.
 * The decision is written by preflight (from the real /health providers) and read by later stages.
 */
export function correctionMode(): "voice" | "typed" {
  try {
    const p = JSON.parse(fs.readFileSync(path.join(config.paths.runtime, "preflight.json"), "utf8"));
    if (p.correctionMode) return p.correctionMode;
  } catch { /* fall through */ }
  const haveFixture = fs.existsSync(path.join(config.paths.fixtures, config.fixtures.correction));
  return config.env.providerMode === "live" && config.env.allowPaidApis && haveFixture ? "voice" : "typed";
}
