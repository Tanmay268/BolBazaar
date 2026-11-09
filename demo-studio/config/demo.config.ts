import "dotenv/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, "..");
export const REPO = path.resolve(ROOT, "..");

const env = (k: string, d = "") => (process.env[k] ?? d).trim();
const bool = (k: string, d = false) => ["1", "true", "yes"].includes(env(k, d ? "true" : "false").toLowerCase());
const flag = (n: string) => process.argv.includes(`--${n}`);
const num = (k: string, d: number) => (Number.isFinite(Number(env(k))) && env(k) !== "" ? Number(env(k)) : d);

export const config = {
  paths: {
    root: ROOT,
    repo: REPO,
    backend: path.join(REPO, "backend"),
    web: path.join(REPO, "web"),
    runtime: path.join(ROOT, ".runtime"),
    fixtures: path.join(ROOT, "fixtures"),
    voice: path.join(ROOT, "assets", "generated-voice"),
    subtitles: path.join(ROOT, "assets", "subtitles"),
    music: path.join(ROOT, "assets", "music"),
    rawRecordings: path.join(ROOT, "recordings", "raw"),
    sceneRecordings: path.join(ROOT, "recordings", "scenes"),
    artifacts: path.join(ROOT, "artifacts", "demo"),
    debug: path.join(ROOT, "artifacts", "demo", "debug"),
  },
  env: {
    manage: bool("DEMO_MANAGE_ENV", true),
    webUrl: env("DEMO_WEB_URL", "http://127.0.0.1:5273"),
    apiUrl: env("DEMO_API_URL", "http://127.0.0.1:8100"),
    allowRemote: bool("DEMO_ALLOW_REMOTE", false),
    providerMode: env("DEMO_PROVIDER_MODE", "offline") as "offline" | "live",
    allowPaidApis: bool("DEMO_ALLOW_PAID_APIS", false),
    maxPaidCalls: num("DEMO_MAX_PAID_CALLS", 12),
  },
  accounts: {
    rep: { username: env("DEMO_REP_USER", "asha"), password: env("DEMO_REP_PASSWORD", "demo123") },
    manager: { username: env("DEMO_MANAGER_USER", "meera"), password: env("DEMO_MANAGER_PASSWORD", "demo123") },
  },
  // What the demo is expected to produce. Verified against the live UI; the run fails if the app disagrees.
  expect: {
    retailer: "Sharma General Store",
    firstProduct: "Parle-G",
    secondProduct: "Real Mango",
    initialQty: 20,
    correctedQty: 15,
    secondQty: 10,
    paymentRupees: 5000,
    visitDate: "next Monday",
    correctionText: "Parle-G 15 kar do", // used only when voice correction is not possible (offline STT stub)
    managerQuestion: "Which retailers have overdue payments?",
  },
  fixtures: { order: "rep-order.wav", correction: "correction.wav" },
  browser: {
    headed: bool("DEMO_HEADED", false) || flag("headed"),
    debug: bool("DEMO_DEBUG", false) || flag("debug"),
    phone: { width: 430, height: 932 },
    desktop: { width: 1920, height: 1080 },
  },
  video: { width: 1920, height: 1080, fps: 30, minSeconds: 75, maxSeconds: 90, websiteUrl: env("DEMO_WEBSITE_URL") },
  tts: {
    provider: env("TTS_PROVIDER", "edge") as "edge" | "elevenlabs" | "sapi" | "none",
    edgeVoice: env("EDGE_VOICE", "en-IN-NeerjaExpressiveNeural"),
    elevenKey: env("ELEVENLABS_API_KEY"),
    elevenVoice: env("ELEVENLABS_VOICE_ID"),
    elevenModel: env("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
    maxChars: num("TTS_MAX_CHARS_PER_RUN", 2500),
    maxRequests: num("TTS_MAX_REQUESTS_PER_RUN", 12),
  },
};

export type Config = typeof config;

export function isLocalUrl(u: string) {
  try { const h = new URL(u).hostname; return h === "localhost" || h === "127.0.0.1" || h === "::1"; } catch { return false; }
}
