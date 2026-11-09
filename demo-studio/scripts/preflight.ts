import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { config, isLocalUrl } from "../config/demo.config.js";
import { fixture } from "../lib/fixtures.js";
import { ensureDir, log, writeJson } from "../lib/log.js";
import { fetchHealth, webUp } from "../lib/stack.js";

export interface Check { name: string; ok: boolean; detail: string; fatal?: boolean }

const has = (cmd: string) => spawnSync(cmd, ["-version"], { encoding: "utf8" }).status === 0;

/** Estimated paid calls for one run in live mode: order STT+LLM, correction (STT+LLM or LLM), reply TTS, manager ask LLM. */
export const estimatedPaidCalls = (voiceCorrection: boolean) => 2 + (voiceCorrection ? 2 : 1) + 1 + 1;

async function login(role: "rep" | "manager") {
  const a = config.accounts[role];
  try {
    const r = await fetch(`${config.env.apiUrl}/v1/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ username: a.username, password: a.password }), signal: AbortSignal.timeout(8000) });
    if (!r.ok) return `login rejected (HTTP ${r.status})`;
    const j = (await r.json()) as { user?: { role?: string } };
    return j.user?.role === role ? null : `account has role "${j.user?.role}", expected "${role}"`;
  } catch (e: any) { return `login failed: ${e.message}`; }
}

/**
 * Checks configuration, tools, fixtures and (when reachable) the running app and demo accounts.
 * `appRunning` = the app is expected to be up (run-demo starts it first); otherwise a managed environment is only checked for prerequisites.
 */
export async function preflight({ appRunning = false } = {}): Promise<{ checks: Check[]; ok: boolean; correctionMode: "voice" | "typed"; providers: string }> {
  const checks: Check[] = [];
  const add = (name: string, ok: boolean, detail: string, fatal = true) => checks.push({ name, ok, detail, fatal });
  const { env, tts, paths } = config;

  add("node >= 20", Number(process.versions.node.split(".")[0]) >= 20, process.version);
  add("ffmpeg", has("ffmpeg"), has("ffmpeg") ? "found" : "not on PATH (install FFmpeg)");
  add("ffprobe", has("ffprobe"), has("ffprobe") ? "found" : "not on PATH");
  let chromiumOk = false;
  try { chromiumOk = fs.existsSync(chromium.executablePath()); } catch { /* not installed */ }
  add("playwright chromium", chromiumOk, chromiumOk ? "installed" : "run: npx playwright install chromium");

  // ---- safety ----
  const local = isLocalUrl(env.apiUrl) && isLocalUrl(env.webUrl);
  add("environment is local or explicitly allowed", local || env.allowRemote, local ? "localhost" : env.allowRemote ? "remote allowed by DEMO_ALLOW_REMOTE=true (use a staging stack, never production)" : `${env.apiUrl} is remote; set DEMO_ALLOW_REMOTE=true only for a dedicated demo/staging environment`);
  const live = env.providerMode === "live";
  add("paid APIs gated", !live || env.allowPaidApis, live ? (env.allowPaidApis ? `live mode allowed, budget ${env.maxPaidCalls} calls` : "DEMO_PROVIDER_MODE=live requires DEMO_ALLOW_PAID_APIS=true") : "offline providers, no paid calls");

  // ---- fixtures ----
  let order = "", correctionFx = false;
  try { const f = fixture(config.fixtures.order); order = `${f.seconds.toFixed(1)}s, ${f.sampleRate} Hz, ${f.channels} ch`; add("fixture rep-order.wav", true, order); }
  catch (e: any) { add("fixture rep-order.wav", false, e.message); }
  try { const f = fixture(config.fixtures.correction); correctionFx = true; add("fixture correction.wav", true, `${f.seconds.toFixed(1)}s`, false); }
  catch { add("fixture correction.wav", true, "absent: the correction will be typed through the app's correction field (spoken correction needs live speech + this fixture)", false); }

  // ---- narration ----
  if (tts.provider === "elevenlabs") add("ElevenLabs configured", !!(tts.elevenKey && tts.elevenVoice), tts.elevenKey && tts.elevenVoice ? "key and voice id present" : "set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID (or use TTS_PROVIDER=edge)");
  else add("TTS provider", tts.provider !== "none", `${tts.provider}${tts.provider === "edge" ? ` (${tts.edgeVoice}, free, needs internet; sends only the public narration script)` : ""}`);

  // ---- app ----
  let providers = `${env.providerMode} (managed)`;
  if (appRunning || !env.manage) {
    const h = await fetchHealth();
    add("API reachable", !!h, h ? `${env.apiUrl} ${h.status}` : `${env.apiUrl}/health unreachable`);
    add("web app reachable", await webUp(), env.webUrl);
    if (h) {
      providers = h.providers;
      const running = /speech=live|reasoner=live/.test(h.providers);
      add("providers match config", running === live, `${h.providers} vs DEMO_PROVIDER_MODE=${env.providerMode}`, true);
      for (const role of ["rep", "manager"] as const) { const err = await login(role); add(`${role} demo account ready`, !err, err ?? `${config.accounts[role].username} can sign in`); }
    }
  } else {
    const py = path.join(paths.backend, ".venv", "Scripts", "python.exe");
    add("backend venv", fs.existsSync(py), fs.existsSync(py) ? "backend/.venv found" : "run: cd backend && uv sync");
    add("web dependencies", fs.existsSync(path.join(paths.web, "node_modules", "vite")), "web/node_modules/vite");
    add("demo accounts", true, "verified after the isolated environment starts (npm run demo:all)", false);
  }

  const voice = live && env.allowPaidApis && correctionFx;
  if (live) add("paid call budget", estimatedPaidCalls(voice) <= env.maxPaidCalls, `~${estimatedPaidCalls(voice)} calls expected, limit ${env.maxPaidCalls} (DEMO_MAX_PAID_CALLS)`);

  const mode = voice ? "voice" : "typed";
  ensureDir(paths.runtime);
  const ok = checks.every((c) => c.ok || !c.fatal);
  writeJson(path.join(paths.runtime, "preflight.json"), { checkedAt: new Date().toISOString(), providers, correctionMode: mode, ok, checks });
  return { checks, ok, correctionMode: mode, providers };
}

export function printChecks(checks: Check[]) {
  for (const c of checks) (c.ok ? log.ok : c.fatal ? log.fail : log.warn)(`${c.name}: ${c.detail}`);
}

if (process.argv[1]?.endsWith("preflight.ts")) {
  preflight().then((r) => { printChecks(r.checks); log.info(`Correction mode: ${r.correctionMode} · providers: ${r.providers}`); process.exit(r.ok ? 0 : 1); })
    .catch((e) => { log.fail(String(e.message ?? e)); process.exit(1); });
}
