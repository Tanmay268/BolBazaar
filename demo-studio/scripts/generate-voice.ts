import fs from "node:fs";
import path from "node:path";
import { SCENES, SPOKEN_CORRECTION_LINE, type Line, type SceneId } from "../config/scenes.js";
import { config } from "../config/demo.config.js";
import { ensureDir, log, readJson, writeJson } from "../lib/log.js";
import { ffprobe } from "../lib/media.js";
import { clipHash, getProvider } from "../lib/tts.js";
import { correctionMode } from "../lib/mode.js";

export interface Clip { sceneId: SceneId; index: number; text: string; subtitle: string; file: string; duration: number; source: "cache" | "generated" | "manual" }
export interface VoiceManifest { provider: string; fingerprint: string; correctionMode: "voice" | "typed"; clips: Clip[] }
export const manifestPath = () => path.join(config.paths.voice, "manifest.json");

export async function generateVoice({ force = false } = {}): Promise<VoiceManifest> {
  const provider = getProvider();
  const mode = correctionMode();
  ensureDir(config.paths.voice);
  const manualDir = path.join(config.paths.voice, "manual");
  let requests = 0, chars = 0;
  const clips: Clip[] = [];

  for (const scene of SCENES) {
    const lines: Line[] = scene.id === "correction" && mode === "voice" ? [SPOKEN_CORRECTION_LINE] : scene.lines;
    for (let i = 0; i < lines.length; i++) {
      const { text, subtitle } = lines[i];
      const manual = ["mp3", "wav", "m4a"].map((e) => path.join(manualDir, `${scene.id}-${i + 1}.${e}`)).find(fs.existsSync);
      let file: string, source: Clip["source"];
      if (manual) { file = manual; source = "manual"; }
      else {
        file = path.join(config.paths.voice, `${scene.id}-${i + 1}.${clipHash(provider, text)}.${provider.ext}`);
        const cached = fs.existsSync(file) && fs.statSync(file).size > 1000;
        if (cached && !force) source = "cache";
        else {
          // spending guard: only paid providers are limited, but the request ceiling protects every provider
          if (requests + 1 > config.tts.maxRequests || chars + text.length > config.tts.maxChars)
            throw new Error(`TTS limits reached (TTS_MAX_REQUESTS_PER_RUN=${config.tts.maxRequests}, TTS_MAX_CHARS_PER_RUN=${config.tts.maxChars}). Raise them in .env to continue.`);
          log.info(`TTS ${provider.name}: ${scene.id}-${i + 1} (${text.length} chars)`);
          await provider.synthesize(text, file);
          requests++; chars += text.length; source = "generated";
        }
      }
      const duration = ffprobe(file).duration;
      if (!(duration > 0.5)) throw new Error(`Narration clip ${file} has no audio`);
      clips.push({ sceneId: scene.id, index: i, text, subtitle, file, duration, source });
    }
  }
  const manifest: VoiceManifest = { provider: provider.name, fingerprint: provider.fingerprint(), correctionMode: mode, clips };
  writeJson(manifestPath(), manifest);
  const total = clips.reduce((s, c) => s + c.duration, 0);
  log.ok(`Narration ready: ${clips.length} clips, ${total.toFixed(1)}s (${requests} synthesised, ${clips.length - requests} cached/manual, provider ${provider.name})`);
  return manifest;
}

export const loadManifest = () => readJson<VoiceManifest>(manifestPath());

if (process.argv[1]?.endsWith("generate-voice.ts")) {
  generateVoice({ force: process.argv.includes("--force") }).catch((e) => { log.fail(String(e.message ?? e)); process.exit(1); });
}
