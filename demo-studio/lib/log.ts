import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";

export const log = {
  info: (m: string) => console.log(`\x1b[36m●\x1b[0m ${m}`),
  ok: (m: string) => console.log(`\x1b[32m✔\x1b[0m ${m}`),
  warn: (m: string) => console.warn(`\x1b[33m!\x1b[0m ${m}`),
  fail: (m: string) => console.error(`\x1b[31m✘\x1b[0m ${m}`),
};

export function ensureDir(d: string) { fs.mkdirSync(d, { recursive: true }); return d; }
export function writeJson(file: string, data: unknown) { ensureDir(path.dirname(file)); fs.writeFileSync(file, JSON.stringify(data, null, 2)); }
export function readJson<T>(file: string): T { return JSON.parse(fs.readFileSync(file, "utf8")) as T; }
export function debugDir() { return config.browser.debug ? ensureDir(config.paths.debug) : null; }
