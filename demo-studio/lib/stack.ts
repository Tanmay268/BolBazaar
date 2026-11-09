import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { config, isLocalUrl } from "../config/demo.config.js";
import { ensureDir, log } from "./log.js";

export interface Health { status: string; providers: string }

export async function fetchHealth(apiUrl = config.env.apiUrl): Promise<Health | null> {
  try {
    const r = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(4000) });
    return r.ok ? ((await r.json()) as Health) : null;
  } catch { return null; }
}
export async function webUp(url = config.env.webUrl) {
  try { return (await fetch(url, { signal: AbortSignal.timeout(4000) })).ok; } catch { return false; }
}

async function waitFor(fn: () => Promise<boolean>, what: string, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await fn()) return; await new Promise((r) => setTimeout(r, 500)); }
  throw new Error(`Timed out waiting for ${what}`);
}

const pidFile = () => path.join(config.paths.runtime, "stack.pids.json");
const killTree = (pid: number) => { try { spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" }); } catch { /* gone */ } };

export interface Stack { started: boolean; stop: () => void }

/** Starts an isolated backend + web dev server (throw-away SQLite DB, offline providers unless explicitly allowed live). */
export async function ensureStack({ reset = true } = {}): Promise<Stack> {
  const { env, paths } = config;
  const health = await fetchHealth();
  if (health && (await webUp())) { log.info(`Re-using running environment (${health.providers})`); return { started: false, stop() {} }; }
  if (!env.manage) throw new Error(`Environment is not running at ${env.apiUrl} / ${env.webUrl} and DEMO_MANAGE_ENV=false.`);
  if (!isLocalUrl(env.apiUrl) || !isLocalUrl(env.webUrl)) throw new Error("Refusing to start a managed environment on a non-local URL.");
  ensureDir(paths.runtime);
  const live = env.providerMode === "live";
  if (live && !env.allowPaidApis) throw new Error("DEMO_PROVIDER_MODE=live needs DEMO_ALLOW_PAID_APIS=true (it spends Gnani/Azure credits).");

  const db = path.join(paths.runtime, "demo.db");
  if (reset) for (const f of [db, `${db}-wal`, `${db}-shm`]) fs.rmSync(f, { force: true });
  const audio = ensureDir(path.join(paths.runtime, "audio"));
  const api = new URL(env.apiUrl), web = new URL(env.webUrl);
  const py = path.join(paths.backend, ".venv", "Scripts", "python.exe");
  const mode = live ? "live" : "offline";
  const blank = live ? {} : { GNANI_API_KEY: "", AZURE_OPENAI_API_KEY: "", AZURE_OPENAI_ENDPOINT: "", AZURE_OPENAI_DEPLOYMENT: "" };
  const backendEnv = {
    ...process.env, ...blank,
    APP_ENV: "development", SEED_DEMO_DATA: "true", HOST: api.hostname, PORT: api.port || "8100",
    DATABASE_URL: `sqlite:///${db.split(path.sep).join("/")}`, AUDIO_STORAGE_DIR: audio,
    CORS_ORIGINS: `${web.origin},http://localhost:${web.port}`, APP_BASE_URL: env.apiUrl,
    PROVIDER_MODE: mode, SPEECH_MODE: mode, REASONER_MODE: mode, DEMO_PASSWORD: config.accounts.rep.password,
    // Even in live mode keep the studio inside a small per-run budget (server-side kill switch for the demo instance).
    GNANI_DAILY_CALL_BUDGET: String(env.maxPaidCalls),
  } as NodeJS.ProcessEnv;
  const out = (n: string) => fs.openSync(path.join(paths.runtime, n), "w");
  const procs: ChildProcess[] = [];
  const b = spawn(py, ["-c", "from bolbazaar.main import run; run()"], { cwd: paths.backend, env: backendEnv, stdio: ["ignore", out("backend.log"), out("backend.log")], windowsHide: true });
  procs.push(b);
  const w = spawn(process.execPath, [path.join(paths.web, "node_modules", "vite", "bin", "vite.js"), "--port", web.port, "--host", web.hostname, "--strictPort"],
    { cwd: paths.web, env: { ...process.env, VITE_API_URL: env.apiUrl }, stdio: ["ignore", out("web.log"), out("web.log")], windowsHide: true });
  procs.push(w);
  fs.writeFileSync(pidFile(), JSON.stringify(procs.map((p) => p.pid)));
  const stop = () => { procs.forEach((p) => p.pid && killTree(p.pid)); fs.rmSync(pidFile(), { force: true }); };
  try {
    await waitFor(async () => !!(await fetchHealth()), "backend /health");
    await waitFor(() => webUp(), "web dev server");
  } catch (e) { stop(); throw e; }
  log.ok(`Started isolated environment: API ${env.apiUrl}, web ${env.webUrl} (${mode} providers, DB ${path.relative(config.paths.root, db)})`);
  return { started: true, stop };
}

/** Kills processes left behind by a crashed run. */
export function killStale() {
  try {
    const pids = JSON.parse(fs.readFileSync(pidFile(), "utf8")) as number[];
    pids.forEach(killTree); fs.rmSync(pidFile(), { force: true });
  } catch { /* nothing */ }
}
