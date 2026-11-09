import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { ensureDir } from "./log.js";

/** A TTS provider turns text into an audio file. Add another provider by implementing this and registering it below. */
export interface TtsProvider {
  name: string;
  /** Identifies voice + model so cached clips are invalidated when either changes. */
  fingerprint(): string;
  ext: string;
  /** Number of billable requests this provider makes per synthesize() call. */
  paid: boolean;
  synthesize(text: string, outFile: string): Promise<void>;
}

const edge: TtsProvider = {
  name: "edge", ext: "mp3", paid: false,
  fingerprint: () => `edge:${config.tts.edgeVoice}`,
  async synthesize(text, outFile) {
    const { MsEdgeTTS, OUTPUT_FORMAT } = await import("msedge-tts");
    const tts = new MsEdgeTTS();
    await tts.setMetadata(config.tts.edgeVoice, OUTPUT_FORMAT.AUDIO_24KHZ_96KBITRATE_MONO_MP3);
    const dir = ensureDir(path.join(config.paths.runtime, "tts-tmp"));
    const res: any = await tts.toFile(dir, text);
    const produced: string = typeof res === "string" ? res : res.audioFilePath;
    fs.copyFileSync(produced, outFile);
  },
};

const elevenlabs: TtsProvider = {
  name: "elevenlabs", ext: "mp3", paid: true,
  fingerprint: () => `elevenlabs:${config.tts.elevenVoice}:${config.tts.elevenModel}`,
  async synthesize(text, outFile) {
    const { elevenKey, elevenVoice, elevenModel } = config.tts;
    if (!elevenKey || !elevenVoice) throw new Error("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required for TTS_PROVIDER=elevenlabs");
    const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${elevenVoice}?output_format=mp3_44100_128`, {
      method: "POST", headers: { "xi-api-key": elevenKey, "content-type": "application/json", accept: "audio/mpeg" },
      body: JSON.stringify({ text, model_id: elevenModel, voice_settings: { stability: 0.5, similarity_boost: 0.8, style: 0.2 } }),
      signal: AbortSignal.timeout(60000),
    });
    if (!r.ok) throw new Error(`ElevenLabs HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
    fs.writeFileSync(outFile, Buffer.from(await r.arrayBuffer()));
  },
};

/** Offline fallback: the local Windows speech engine (English voices only; Hinglish is read with an English accent). */
const sapi: TtsProvider = {
  name: "sapi", ext: "wav", paid: false,
  fingerprint: () => "sapi:default",
  async synthesize(text, outFile) {
    const script = `Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate=-1; $s.SetOutputToWaveFile($env:OUT); $s.Speak($env:TXT); $s.Dispose()`;
    const r = spawnSync("powershell", ["-NoProfile", "-Command", script], { env: { ...process.env, OUT: outFile, TXT: text }, encoding: "utf8" });
    if (r.status !== 0) throw new Error(`SAPI failed: ${r.stderr}`);
  },
};

export function getProvider(): TtsProvider {
  const p = { edge, elevenlabs, sapi }[config.tts.provider as "edge"];
  if (!p) throw new Error(`TTS_PROVIDER=${config.tts.provider} is not available (use edge, elevenlabs or sapi). Drop pre-recorded clips into assets/generated-voice/manual/<scene>-<n>.mp3 for the manual fallback.`);
  return p;
}

export const clipHash = (provider: TtsProvider, text: string) =>
  crypto.createHash("sha256").update(`${provider.fingerprint()}\n${text}`).digest("hex").slice(0, 12);
