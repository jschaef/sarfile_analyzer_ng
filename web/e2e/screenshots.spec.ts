import path from "node:path";
import { expect, test } from "@playwright/test";
import { deleteFile, login, renderedCharts, upload } from "./helpers";

// Documentation screenshots (synthetic data only):
//   SAR_SCREENSHOTS_DIR=docs/screenshots npx playwright test screenshots
const outDir = process.env.SAR_SCREENSHOTS_DIR;
const width = Number(process.env.SAR_SCREENSHOTS_WIDTH ?? 1280);

test.skip(!outDir, "SAR_SCREENSHOTS_DIR not set");

for (const scheme of ["light", "dark"] as const) {
  test(`screenshots ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width, height: 900 });

    await page.goto("/login");
    await expect(page.getByLabel("Username")).toBeVisible();
    await page.screenshot({ path: path.join(outDir!, `login-${scheme}-${width}.png`) });

    await login(page);
    const name = await upload(page, path.join(__dirname, "fixtures", "sar_small.txt"), "synthetic-host");
    await page.goto(`/overview?file=${encodeURIComponent(name)}`);
    await page.getByTestId("show-diagrams").click();
    await expect(renderedCharts(page)).toHaveCount(5);
    await page.screenshot({ path: path.join(outDir!, `overview-${scheme}-${width}.png`), fullPage: true });
    await deleteFile(page, name);
  });
}
