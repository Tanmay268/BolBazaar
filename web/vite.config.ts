import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";

/**
 * Serves downloads/BolBazaar.apk at /BolBazaar.apk for the website's install link.
 * Skipped for the Capacitor bundle (`--mode app`) so the APK never ends up inside itself.
 */
function apkDownload(): Plugin {
  const file = "downloads/BolBazaar.apk";
  let app = false;
  return {
    name: "apk-download",
    configResolved(c) { app = c.mode === "app"; },
    configureServer(s) {
      s.middlewares.use("/BolBazaar.apk", (_req, res) => {
        if (!existsSync(file)) { res.statusCode = 404; return res.end(); }
        res.setHeader("Content-Type", "application/vnd.android.package-archive");
        res.end(readFileSync(file));
      });
    },
    generateBundle() {
      if (!app && existsSync(file)) this.emitFile({ type: "asset", fileName: "BolBazaar.apk", source: readFileSync(file) });
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), apkDownload()],
  server: { port: 5173, host: true },
  // The Capacitor bundle is built with `--mode app`, which would skip .env.production; take the API URL from it.
  define: mode === "app" ? { "import.meta.env.VITE_API_URL": JSON.stringify(loadEnv("production", process.cwd(), "VITE_").VITE_API_URL ?? "") } : {},
}));
