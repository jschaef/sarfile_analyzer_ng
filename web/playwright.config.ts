import { defineConfig, devices } from "@playwright/test";

// The e2e test needs both servers: the FastAPI from api/ (port 8100) and this
// Next.js app (port 3000, production build: run `npm run build` first).
// Already running servers are reused. Set SAR_E2E_SKIP_API=1 to never start
// the API from here, or SAR_E2E_API_CMD to change how it is started.
const apiCommand =
  process.env.SAR_E2E_API_CMD ?? "uvicorn api.main:app --host 127.0.0.1 --port 8100";
const port = Number(process.env.PORT ?? 3000);

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 900 },
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } }],
  webServer: [
    ...(process.env.SAR_E2E_SKIP_API
      ? []
      : [
          {
            command: apiCommand,
            cwd: "..",
            url: "http://127.0.0.1:8100/api/v1/health",
            reuseExistingServer: true,
            timeout: 120_000,
          },
        ]),
    {
      command: `npx next start -p ${port}`,
      url: `http://127.0.0.1:${port}/login`,
      reuseExistingServer: true,
      timeout: 120_000,
      // plain HTTP in tests: the session cookie must not be Secure
      env: { SAR_COOKIE_SECURE: "false" },
    },
  ],
});
