import fs from "node:fs";
import path from "node:path";
import { config } from "../config/demo.config.js";
import { log } from "../lib/log.js";
import { ensureStack, killStale, type Stack } from "../lib/stack.js";
import { generateVoice } from "./generate-voice.js";
import { preflight, printChecks } from "./preflight.js";
import { recordAll } from "./record-demo.js";
import { renderDemo } from "./generate-video.js";
import { validate, writeReports } from "./validate-output.js";

/**
 * One command: check -> narration -> record real app -> render -> validate -> report.
 *   npm run demo:all                       full run
 *   npm run demo:all -- --scenes=manager   re-record only these scenes (rep-order, rep-correct-confirm, manager)
 *   npm run demo:all -- --skip-record      re-render from existing recordings
 *   npm run demo:all -- --force-voice      regenerate narration (spends TTS requests on paid providers)
 *   npm run demo:all -- --headed --debug   visible browser, screenshots and logs in artifacts/demo/debug
 */
async function main() {
  const args = process.argv.slice(2);
  const arg = (n: string) => args.find((a) => a.startsWith(`--${n}=`))?.split("=")[1];
  const skipRecord = args.includes("--skip-record"), forceVoice = args.includes("--force-voice");
  const only = arg("scenes")?.split(",").filter(Boolean);

  let stack: Stack | undefined;
  try {
    log.info("1/6 Checking configuration, tools, fixtures");
    let pf = await preflight({ appRunning: false });
    printChecks(pf.checks);
    if (!pf.ok) throw new Error("Preflight failed (see above). Nothing was recorded or spent.");

    if (!skipRecord) {
      // never leave a previous run's video or report around to be mistaken for the result of a failed run
      for (const f of ["bolbazaar-demo.mp4", "demo-report.json", "demo-report.md"]) fs.rmSync(path.join(config.paths.artifacts, f), { force: true });
      killStale();
      stack = await ensureStack({ reset: !only?.length });
      log.info("2/6 Verifying the application and demo accounts");
      pf = await preflight({ appRunning: true });
      printChecks(pf.checks.filter((c) => /API|web app|providers|account/.test(c.name)));
      if (!pf.ok) throw new Error("Application is not ready for recording.");
    }

    log.info(`3/6 Narration (${config.tts.provider}, cached clips are reused)`);
    await generateVoice({ force: forceVoice });

    if (!skipRecord) {
      log.info("4/6 Recording the real application");
      const rep = await recordAll(only, stack!);
      if (rep.some((r) => r.status === "failed")) {
        stack!.stop(); stack = undefined;
        const r = validate(); writeReports(r);
        throw new Error(`Recording failed: ${rep.filter((x) => x.status === "failed").map((x) => `${x.name}: ${x.error}`).join(" | ")}. No video was produced; see artifacts/demo/demo-report.md.`);
      }
      stack!.stop(); stack = undefined;
    } else log.info("4/6 Skipped recording (using existing scene recordings)");

    log.info("5/6 Rendering with Remotion and FFmpeg");
    await renderDemo();

    log.info("6/6 Validating the final MP4");
    const report = validate(); writeReports(report);
    for (const c of report.checks) (c.ok ? log.ok : log.fail)(`${c.name}: ${c.detail}`);
    report.notes.forEach((n) => log.warn(n));
    log.info(`Report: artifacts/demo/demo-report.md`);
    if (!report.ok) throw new Error("Validation failed.");
    log.ok(`Done: ${report.output}`);
  } finally { stack?.stop(); }
}

main().catch((e) => { log.fail(String(e.message ?? e)); process.exit(1); });
