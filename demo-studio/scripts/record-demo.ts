import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { config } from "../config/demo.config.js";
import { fixture } from "../lib/fixtures.js";
import { ensureDir, log, writeJson } from "../lib/log.js";
import { correctionMode } from "../lib/mode.js";
import { Session, check, type SceneRecording } from "../lib/session.js";
import { ensureStack, killStale, type Stack } from "../lib/stack.js";

const { env, accounts, expect: want } = config;
const url = (p = "/") => `${env.webUrl}${p}${p.includes("?") ? "&" : "?"}introT=off`;
const stateFile = (role: string) => path.join(config.paths.runtime, `state-${role}.json`);
const rupees = (s: string) => Number(s.replace(/[^\d.]/g, ""));

export interface RunReportScene { name: string; status: "passed" | "failed" | "skipped"; seconds: number; error?: string; facts?: Record<string, unknown> }

/** Signs in through the real login form (no video) and dismisses the first-run tour, saving the auth state for the recorded scenes. */
async function authenticate(role: "rep" | "manager") {
  const browser = await chromium.launch({ headless: !config.browser.headed });
  const ctx = await browser.newContext({ viewport: role === "rep" ? config.browser.phone : config.browser.desktop, locale: "en-IN" });
  const page = await ctx.newPage();
  try {
    await page.goto(url());
    const acct = accounts[role];
    await page.getByLabel("Username").fill(acct.username);
    await page.getByLabel("Password").fill(acct.password);
    await page.getByRole("button", { name: "Sign in" }).last().click();
    await page.waitForFunction(() => !!localStorage.getItem("ff.token"), null, { timeout: 20000 });
    const skip = page.getByRole("button", { name: /^Skip/ });
    if (await skip.isVisible({ timeout: 4000 }).catch(() => false)) await skip.click();
    const user = await page.evaluate(() => JSON.parse(localStorage.getItem("ff.user") ?? "null"));
    if (!user || user.role !== role) throw new Error(`Signed in as ${user?.role ?? "nobody"}, expected ${role}`);
    await ctx.storageState({ path: stateFile(role) });
    log.ok(`Authenticated ${role} through the real login form`);
  } finally { await browser.close(); }
}

async function readApi<T>(token: string, p: string): Promise<T> {
  const r = await fetch(`${env.apiUrl}${p}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`GET ${p} -> ${r.status}`);
  return (await r.json()) as T;
}

// ---------------------------------------------------------------------------------------------------- scene 1+2
async function sceneOrder(): Promise<SceneRecording> {
  const fx = fixture(config.fixtures.order);
  const s = new Session({ name: "rep-order", viewport: config.browser.phone, fakeAudio: fx.path, storageState: stateFile("rep") });
  await s.open();
  const p = s.page;
  try {
    await p.goto(url());
    await p.getByRole("button", { name: "Log a Visit" }).first().waitFor();
    s.mark("home");
    await p.waitForTimeout(900);
    await s.click(p.getByRole("button", { name: "Log a Visit" }).first(), { label: "log-visit" });
    const orb = p.getByRole("button", { name: "Tap to record" });
    await orb.waitFor();
    s.mark("record-screen");
    await p.waitForTimeout(700);
    await s.click(orb, { label: "mic-start" });
    const stop = p.getByRole("button", { name: "Stop recording" });
    await stop.waitFor({ timeout: 10000 }); // real getUserMedia succeeded and the recorder is live
    s.mark("recording-start");
    await s.highlight("mic", stop, 6);
    s.events.push({ t: s.now(), kind: "recording", active: true });
    await p.waitForTimeout(fx.seconds * 1000 + 700); // the fake microphone plays the WAV once
    check(await stop.isVisible(), "recorder still active after the fixture played");
    await s.click(p.getByRole("button", { name: "Stop and send" }), { label: "mic-stop" });
    s.events.push({ t: s.now(), kind: "recording", active: false });
    s.mark("recording-stop");
    await p.getByRole("heading", { name: "Review Visit" }).waitFor({ timeout: 60000 });
    s.mark("extracted");
    await p.waitForTimeout(600);

    // ---- verify the extracted draft against the UI ----
    const rv = p.locator(".rv");
    const rowOf = (label: string) => rv.locator(".rv-row").filter({ hasText: label }).first();
    check((await rowOf("Retailer").innerText()).includes(want.retailer), `retailer is ${want.retailer}`);
    const lines = (await rv.locator(".rv-item").allInnerTexts()).map((t) => t.replace(/\s+/g, " "));
    const parle = lines.find((l) => l.includes(want.firstProduct));
    const mango = lines.find((l) => l.includes("Real"));
    check(parle && new RegExp(`×\\s*${want.initialQty}\\b`).test(parle), `Parle-G × ${want.initialQty} (got: ${lines.join(" | ")})`);
    check(mango && new RegExp(`×\\s*${want.secondQty}\\b`).test(mango), `Real juice × ${want.secondQty} (got: ${lines.join(" | ")})`);
    s.facts.secondItemResolved = !/not in catalogue|new item/.test(mango!);
    if (env.providerMode === "live") check(s.facts.secondItemResolved, `${want.secondProduct} matched the catalogue (live mode)`);
    const total = rupees(await rv.locator(".rv-total b").innerText());
    check(total > 0, "order total shown");
    const amounts = (await rv.locator(".rv-item-amt").allInnerTexts()).map(rupees);
    check(amounts.reduce((a, b) => a + b, 0) === total, `line amounts ${amounts.join("+")} equal total ${total}`);
    s.facts = { ...s.facts, initialTotal: total, items: lines, transcript: await p.locator(".rv-clip").innerText().catch(() => "") };
    check((await rowOf("Payment").innerText()).replace(/,/g, "").includes(String(want.paymentRupees)), `payment ₹${want.paymentRupees} present`);
    check((await rv.innerText()).toLowerCase().includes("complaint"), "complaint row present");

    // ---- highlight real rows, one after another, for the editor ----
    for (const [name, label] of [["retailer", "Retailer"], ["order", "Order"], ["delivery", "Delivery"], ["payment", "Payment"], ["followups", "Follow"], ["complaint", "Complaint"]] as const) {
      const row = rowOf(label);
      if (await row.count()) await s.highlight(name, row, 3);
    }
    await s.glide(rv.locator(".rv-total"), 700);
    await p.waitForTimeout(1200);
    await s.shot("extracted");
    s.mark("verified");
    return (await s.close())!;
  } catch (e) { await s.close(true); throw e; }
}

// ---------------------------------------------------------------------------------------------------- scene 3+4
async function sceneCorrectAndConfirm(): Promise<SceneRecording> {
  const mode = correctionMode();
  const fx = mode === "voice" ? fixture(config.fixtures.correction) : null;
  const s = new Session({ name: "rep-correct-confirm", viewport: config.browser.phone, fakeAudio: fx?.path, storageState: stateFile("rep") });
  await s.open();
  const p = s.page;
  s.facts.correctionMode = mode;
  try {
    await p.goto(url());
    await s.click(p.getByRole("button", { name: "Log a Visit" }).first(), { label: "log-visit" });
    // The draft from the previous scene is waiting for the rep; resuming it is a normal app flow.
    await s.click(p.getByRole("button", { name: /Ready to confirm|Has a question/ }).first(), { label: "resume-draft" });
    await p.getByRole("heading", { name: "Review Visit" }).waitFor({ timeout: 15000 });
    const rv = p.locator(".rv");
    // An ambiguous product ("Real juice") makes the app ask instead of guessing; answering it is a real app flow.
    const ask = p.locator(".block-ask");
    if (await ask.isVisible().catch(() => false)) {
      s.facts.clarificationQuestion = (await ask.locator(".ask-q").innerText()).trim();
      s.mark("clarification");
      await p.waitForTimeout(1200);
      await s.highlight("clarification", ask, 3);
      await s.click(ask.getByRole("button", { name: new RegExp(want.secondProduct, "i") }).first(), { label: "answer-chip" });
      await ask.waitFor({ state: "detached", timeout: 20000 });
      await p.waitForTimeout(900);
      const resolved = (await rv.locator(".rv-item").allInnerTexts()).map((x) => x.replace(/\s+/g, " "));
      check(resolved.some((l) => l.includes(want.secondProduct) && !/not in catalogue/.test(l)), `clarification resolved to ${want.secondProduct} (got: ${resolved.join(" | ")})`);
    }
    const before = rupees(await rv.locator(".rv-total b").innerText());
    s.mark("review");
    await p.waitForTimeout(900);

    await s.click(p.getByRole("button", { name: "Edit", exact: true }), { label: "edit" });
    s.mark("correction-start");
    const notice = p.locator(".notice");
    if (mode === "voice") {
      const hold = p.getByRole("button", { name: /Hold to correct/ });
      await s.glide(hold, 600);
      await p.mouse.down();
      s.events.push({ t: s.now(), kind: "recording", active: true });
      await p.waitForTimeout(fx!.seconds * 1000 + 600);
      await p.mouse.up();
      s.events.push({ t: s.now(), kind: "recording", active: false });
    } else {
      await s.type(p.getByLabel("Type a correction"), want.correctionText);
      await p.waitForTimeout(300);
      await s.click(p.getByRole("button", { name: "Apply correction" }), { label: "apply" });
    }
    s.mark("correction-sent");
    await notice.waitFor({ timeout: 60000 });
    s.mark("corrected");
    const noticeText = (await notice.innerText()).replace(/\s+/g, " ");
    check(!/Couldn't apply|Nothing changed/.test(noticeText), `correction applied (notice: ${noticeText})`);
    await p.waitForTimeout(500);

    // ---- verify corrected quantity and recomputed totals ----
    const lines = (await rv.locator(".rv-item").allInnerTexts()).map((t) => t.replace(/\s+/g, " "));
    const parle = lines.find((l) => l.includes(want.firstProduct));
    check(parle && new RegExp(`×\\s*${want.correctedQty}\\b`).test(parle), `Parle-G × ${want.correctedQty} after correction (got: ${lines.join(" | ")})`);
    const after = rupees(await rv.locator(".rv-total b").innerText());
    const amounts = (await rv.locator(".rv-item-amt").allInnerTexts()).map(rupees);
    check(after < before, `total dropped (${before} -> ${after})`);
    check(amounts.reduce((a, b) => a + b, 0) === after, `recomputed line amounts ${amounts.join("+")} equal total ${after}`);
    s.facts = { ...s.facts, totalBefore: before, totalAfter: after, notice: noticeText, itemsAfter: lines };
    await s.highlight("corrected-item", rv.locator(".rv-item").filter({ hasText: want.firstProduct }).first(), 3);
    await s.highlight("total", rv.locator(".rv-total"), 3);
    await s.highlight("notice", notice, 3);
    await p.waitForTimeout(1800);
    await s.shot("corrected");

    // ---- confirm ----
    const confirm = p.getByRole("button", { name: /^Confirm/ });
    check(await confirm.isEnabled(), "Confirm is enabled");
    await s.highlight("confirm-button", confirm, 3);
    await p.waitForTimeout(900);
    const replyAudio = p.waitForResponse((r) => /reply/.test(r.url()) && r.request().method() === "GET", { timeout: 25000 }).catch(() => null);
    await s.click(confirm, { label: "confirm" });
    s.mark("confirm-clicked");
    await p.getByRole("heading", { name: /Visit\s*Saved/ }).waitFor({ timeout: 30000 });
    s.mark("saved");
    check((await p.locator(".saved").innerText()).includes(want.retailer), "saved screen names the retailer");
    s.facts.confirmationText = await p.locator(".saved-quote").innerText().catch(() => "");
    const reply = await replyAudio;
    if (reply && reply.ok()) {
      const buf = await reply.body();
      if (buf.length > 4000) { const f = path.join(config.paths.runtime, "app-reply.wav"); fs.writeFileSync(f, buf); s.facts.replyAudio = f; s.facts.replyBytes = buf.length; }
    }
    await s.highlight("saved-stats", p.locator(".saved-stats"), 3);
    await p.waitForTimeout(2200);

    // ---- persistence check through the app's own read-only API ----
    const token = await p.evaluate(() => localStorage.getItem("ff.token"));
    check(token, "rep session token present");
    const { orders } = await readApi<{ orders: any[] }>(token!, "/v1/orders?limit=10");
    const saved = orders.find((o) => JSON.stringify(o).includes(want.retailer));
    check(saved, `order for ${want.retailer} persisted (GET /v1/orders)`);
    s.facts.persistedOrder = { id: saved.id };
    s.mark("persisted");
    await s.shot("saved");
    return (await s.close())!;
  } catch (e) { await s.close(true); throw e; }
}

// ---------------------------------------------------------------------------------------------------- scene 6
async function sceneManager(): Promise<SceneRecording> {
  const s = new Session({ name: "manager", viewport: config.browser.desktop, storageState: stateFile("manager") });
  await s.open();
  const p = s.page;
  try {
    await p.goto(url());
    await p.getByRole("heading", { level: 1 }).first().waitFor({ timeout: 20000 });
    await p.waitForLoadState("networkidle").catch(() => undefined);
    s.mark("dashboard");
    await p.waitForTimeout(1500);
    const panel = p.locator(".mpanel").first();
    if (await panel.count()) { await s.highlight("panels", panel, 3); await s.glide(panel, 900); }
    await p.waitForTimeout(1500);
    s.facts.dashboardText = (await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 600);

    await s.click(p.getByRole("button", { name: "Ask", exact: true }).first(), { label: "nav-ask" });
    const input = p.getByRole("textbox", { name: "Ask" });
    await input.waitFor();
    s.mark("ask-screen");
    await p.waitForTimeout(700);
    await s.type(input, want.managerQuestion, 45);
    await p.waitForTimeout(400);
    await s.click(p.locator(".ask-go"), { label: "ask-go" });
    s.mark("asked");
    const answer = p.locator(".answer");
    await answer.waitFor({ timeout: 40000 });
    s.mark("answered");
    await p.waitForTimeout(700);
    const text = (await answer.innerText()).replace(/\s+/g, " ");
    check(text.length > 10, "manager answer is not empty");
    s.facts.answer = text.slice(0, 500);
    await s.highlight("answer", answer, 4);
    await p.waitForTimeout(3200);
    await s.shot("answer");

    // the visit saved by the rep must be visible to the manager (read-only API check)
    const token = await p.evaluate(() => localStorage.getItem("ff.token"));
    const { orders } = await readApi<{ orders: any[] }>(token!, "/v1/orders?limit=20");
    check(orders.some((o) => JSON.stringify(o).includes(want.retailer)), `manager can see the ${want.retailer} order`);
    s.facts.managerSeesOrder = true;
    s.mark("verified");
    return (await s.close())!;
  } catch (e) { await s.close(true); throw e; }
}

// ---------------------------------------------------------------------------------------------------- runner
const SCENE_RUNNERS: Record<string, () => Promise<SceneRecording>> = {
  "rep-order": sceneOrder, "rep-correct-confirm": sceneCorrectAndConfirm, manager: sceneManager,
};

export async function recordAll(only?: string[], shared?: Stack): Promise<RunReportScene[]> {
  if (!shared) killStale();
  ensureDir(config.paths.runtime); ensureDir(config.paths.sceneRecordings);
  const stack = shared ?? await ensureStack({ reset: !only?.length }); // a partial re-run keeps the data created by earlier scenes
  const report: RunReportScene[] = [];
  try {
    const names = only?.length ? only : Object.keys(SCENE_RUNNERS);
    // tokens die with the backend process (random per-process JWT secret), so always sign in again after a fresh start
    const fresh = stack.started || !only?.length;
    if (fresh || !fs.existsSync(stateFile("rep"))) await authenticate("rep");
    if (fresh || !fs.existsSync(stateFile("manager"))) await authenticate("manager");
    for (const name of names) {
      const t = Date.now();
      log.info(`Recording scene "${name}"`);
      try {
        const rec = await SCENE_RUNNERS[name]();
        if (rec.errors.length) throw new Error(`browser errors during scene: ${rec.errors.slice(0, 3).join(" ; ")}`);
        report.push({ name, status: "passed", seconds: (Date.now() - t) / 1000, facts: rec.facts });
        log.ok(`${name}: ${rec.duration.toFixed(1)}s of video`);
      } catch (e: any) {
        report.push({ name, status: "failed", seconds: (Date.now() - t) / 1000, error: String(e.message ?? e) });
        log.fail(`${name}: ${e.message ?? e}`);
        break; // later scenes depend on earlier ones: never produce a misleading partial demo
      }
    }
  } finally { if (!shared) stack.stop(); }
  // merge with the previous report so a partial re-run still reports every scene
  const file = path.join(config.paths.runtime, "record-report.json");
  let merged = report;
  if (only?.length) {
    try {
      const prev = JSON.parse(fs.readFileSync(file, "utf8")) as RunReportScene[];
      merged = Object.keys(SCENE_RUNNERS).map((n) => report.find((r) => r.name === n) ?? prev.find((r) => r.name === n)).filter(Boolean) as RunReportScene[];
    } catch { /* no previous report */ }
  }
  writeJson(file, merged);
  return report;
}

if (process.argv[1]?.endsWith("record-demo.ts")) {
  const only = process.argv.slice(2).filter((a) => !a.startsWith("-"));
  recordAll(only).then((r) => { if (r.some((x) => x.status === "failed")) process.exit(1); }).catch((e) => { log.fail(String(e.message ?? e)); process.exit(1); });
}
