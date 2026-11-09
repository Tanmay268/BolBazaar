import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { log } from "../lib/log.js";
import { killStale } from "../lib/stack.js";

/**
 * Removes everything the studio created in its own isolated environment: the throw-away SQLite database, stored audio,
 * saved auth state and raw recordings. It never touches the main backend database or any remote environment: demo
 * records only ever live in demo-studio/.runtime/demo.db (see README, "Cleaning up demo data").
 */
export function cleanup({ keepArtifacts = true } = {}) {
  killStale();
  const targets = [config.paths.runtime, config.paths.rawRecordings, path.join(config.paths.root, "public")];
  if (!keepArtifacts) targets.push(config.paths.sceneRecordings, config.paths.artifacts);
  for (const t of targets) { fs.rmSync(t, { recursive: true, force: true }); log.ok(`removed ${path.relative(config.paths.root, t)}`); }
  if (!config.env.manage || !/127\.0\.0\.1|localhost/.test(config.env.apiUrl))
    log.warn("DEMO_MANAGE_ENV=false: records created in the external environment are NOT removed automatically. Delete them there (README: Cleaning up demo data).");
}

if (process.argv[1]?.endsWith("cleanup.ts")) cleanup({ keepArtifacts: !process.argv.includes("--all") });
