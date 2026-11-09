import { chromium, type Browser, type BrowserContext, type Locator, type Page } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { ensureDir, log, writeJson } from "./log.js";
import { ffmpeg, ffprobe } from "./media.js";

export interface Box { x: number; y: number; w: number; h: number }
export interface TimelineEvent {
  t: number; kind: "cursor" | "click" | "mark" | "box" | "type" | "recording";
  name?: string; x?: number; y?: number; box?: Box; text?: string; dur?: number; active?: boolean;
}
export interface SceneRecording {
  name: string; file: string; duration: number; viewport: { width: number; height: number };
  events: TimelineEvent[]; markers: Record<string, number>; errors: string[]; facts: Record<string, unknown>;
}

export interface SessionOptions {
  name: string; viewport: { width: number; height: number };
  fakeAudio?: string; storageState?: string; record?: boolean; mobile?: boolean; scale?: number;
}

/** One browser + one recorded page, with a timeline of semantic events (cursor path, clicks, boxes, markers). */
export class Session {
  browser!: Browser; context!: BrowserContext; page!: Page;
  events: TimelineEvent[] = []; markers: Record<string, number> = {}; errors: string[] = []; facts: Record<string, unknown> = {};
  private t0 = 0; private cursor = { x: 0, y: 0 };
  constructor(public opts: SessionOptions) {}

  now() { return (Date.now() - this.t0) / 1000; }

  async open() {
    const { opts } = this;
    const args = ["--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"];
    if (opts.fakeAudio) args.push("--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${opts.fakeAudio}%noloop`);
    this.browser = await chromium.launch({ headless: !config.browser.headed, args });
    const rawDir = ensureDir(path.join(config.paths.rawRecordings, opts.name));
    fs.rmSync(rawDir, { recursive: true, force: true }); ensureDir(rawDir);
    this.context = await this.browser.newContext({
      viewport: opts.viewport, permissions: ["microphone"], storageState: opts.storageState, deviceScaleFactor: opts.scale ?? 1,
      locale: "en-IN", timezoneId: "Asia/Kolkata", acceptDownloads: false, isMobile: false,
      ...(opts.record === false ? {} : { recordVideo: { dir: rawDir, size: { width: opts.viewport.width * (opts.scale ?? 1), height: opts.viewport.height * (opts.scale ?? 1) } } }),
    });
    this.t0 = Date.now();
    this.page = await this.context.newPage();
    this.page.on("pageerror", (e) => this.errors.push(`pageerror: ${e.message}`));
    this.page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource.*(401|404)/.test(m.text())) this.errors.push(`console: ${m.text().slice(0, 300)}`); });
    this.page.on("response", (r) => { if (r.status() >= 500) this.errors.push(`http ${r.status()} ${new URL(r.url()).pathname}`); });
  }

  mark(name: string) { this.markers[name] = this.now(); this.events.push({ t: this.now(), kind: "mark", name }); log.info(`  [${this.opts.name}] ${name} @ ${this.now().toFixed(1)}s`); }

  async boxOf(l: Locator): Promise<Box> {
    // bounded: an animated element (pulsing mic) must never stall the recording clock
    await l.scrollIntoViewIfNeeded({ timeout: 1500 }).catch(() => undefined);
    const b = await l.boundingBox(); if (!b) throw new Error("element has no box");
    return { x: b.x, y: b.y, w: b.width, h: b.height };
  }

  /** Records a highlight rectangle for a real element, visible from now on for `dur` seconds. */
  async highlight(name: string, l: Locator, dur = 2.5) {
    const box = await this.boxOf(l);
    this.events.push({ t: this.now(), kind: "box", name, box, dur });
    return box;
  }

  /** Glides the (real) mouse to the element and records the cursor path so it can be drawn in the final video. */
  async glide(l: Locator, ms = 650) {
    const b = await this.boxOf(l);
    const x = b.x + b.w / 2, y = b.y + Math.min(b.h / 2, 40);
    const t = this.now();
    this.events.push({ t, kind: "cursor", x: this.cursor.x || x, y: this.cursor.y || y });
    const steps = Math.max(8, Math.round(ms / 16));
    const start = Date.now();
    await this.page.mouse.move(x, y, { steps });
    const rest = ms - (Date.now() - start); if (rest > 0) await this.page.waitForTimeout(rest);
    this.cursor = { x, y };
    this.events.push({ t: this.now(), kind: "cursor", x, y });
    return { x, y };
  }

  async click(l: Locator, opts: { ms?: number; label?: string } = {}) {
    await this.glide(l, opts.ms);
    await this.page.waitForTimeout(140);
    this.events.push({ t: this.now(), kind: "click", x: this.cursor.x, y: this.cursor.y, name: opts.label });
    await l.click({ timeout: 10000 });
  }

  async type(l: Locator, text: string, perKey = 55) {
    await this.click(l, { label: "focus" });
    const t = this.now();
    await l.pressSequentially(text, { delay: perKey });
    this.events.push({ t, kind: "type", text, dur: this.now() - t });
  }


  async shot(name: string) {
    if (!config.browser.debug) return;
    ensureDir(config.paths.debug);
    await this.page.screenshot({ path: path.join(config.paths.debug, `${this.opts.name}-${name}.png`) }).catch(() => undefined);
  }

  async close(failed = false): Promise<SceneRecording | null> {
    const video = this.page.video();
    if (failed) await this.shot("failure");
    await this.page.waitForTimeout(failed ? 0 : 500);
    await this.context.close();
    await this.browser.close();
    if (!video) return null;
    const webm = await video.path();
    const outDir = ensureDir(config.paths.sceneRecordings);
    const mp4 = path.join(outDir, `${this.opts.name}.mp4`);
    ffmpeg(["-i", webm, "-r", String(config.video.fps), "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", mp4]);
    const duration = ffprobe(mp4).duration;
    const rec: SceneRecording = { name: this.opts.name, file: mp4, duration, viewport: this.opts.viewport, events: this.events, markers: this.markers, errors: this.errors, facts: this.facts };
    writeJson(path.join(outDir, `${this.opts.name}.json`), rec);
    return rec;
  }
}

/** Throws unless `cond` holds: a failed expectation must stop the pipeline rather than produce a misleading video. */
export function check(cond: unknown, what: string): asserts cond { if (!cond) throw new Error(`Expectation failed: ${what}`); }
