import path from "node:path";
import { expect, test } from "@playwright/test";
import { deleteFile, login, renderedCharts, upload } from "./helpers";

// Optional run against a real sar file that is not part of the repository:
//   SAR_E2E_REAL_FILE=/path/to/sar20260222 SAR_E2E_REAL_HOST=<hostname> npx playwright test real-file
const realFile = process.env.SAR_E2E_REAL_FILE;

test.skip(!realFile, "SAR_E2E_REAL_FILE not set");

test("real sar file: default overview renders", async ({ page }) => {
  await login(page);
  const host = process.env.SAR_E2E_REAL_HOST ?? path.basename(realFile!);
  const name = await upload(page, realFile!, host);
  await page.goto(`/overview?file=${encodeURIComponent(name)}`);
  await page.getByTestId("show-diagrams").click();
  await expect(page.getByTestId("alias-section")).toHaveCount(5);
  await expect(renderedCharts(page)).toHaveCount(5);
  await expect(page.locator("[data-testid=chart-card][data-alias=CPU]")).toContainText(/all of \d+/);
  await deleteFile(page, name);
});
