import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
export default defineConfig({
  testDir: "./tests",
  timeout: 90000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8765",
    channel: process.env.REFIT_TEST_BROWSER || "chrome",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command:
      ".venv\\Scripts\\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765",
    cwd: root,
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 30000,
    env: {
      REFIT_AI_PROVIDER: "manual",
      REFIT_DATA_DIR: root + "/var/browser-tests-" + Date.now(),
    },
  },
});
