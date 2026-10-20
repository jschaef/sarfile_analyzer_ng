import path from "node:path";
import { expect, test } from "@playwright/test";
import { deleteFile, login, renderedCharts, upload } from "./helpers";

const SMALL_FIXTURE = path.join(__dirname, "fixtures", "sar_small.txt");
const DEFAULT_ALIASES = ["CPU", "Kernel tables", "Load", "Memory utilization", "Swap utilization"];

test("login, upload, overview, charts, delete, logout", async ({ page }) => {
  await login(page);

  const name = await upload(page, SMALL_FIXTURE, "synthetic-host");
  expect(name).toMatch(/^\d{4}-\d{2}-\d{2}_synthetic-host_2026-10-01$/);

  // open the overview for exactly this file from the file list
  await page
    .locator(`[data-testid=file-row][data-file="${name}"]`)
    .getByRole("link", { name: "Overview" })
    .click();
  await expect(page).toHaveURL(new RegExp(`/overview\\?file=${name}`));
  await expect(page.getByTestId("file-select")).toHaveValue(name);

  // the Streamlit defaults are preselected
  const pressed = page.getByTestId("alias-pills").locator("button[aria-pressed=true]");
  await expect(pressed).toHaveText(DEFAULT_ALIASES);

  await page.getByTestId("show-diagrams").click();
  const sections = page.getByTestId("alias-section");
  await expect(sections).toHaveCount(5);
  await expect(renderedCharts(page)).toHaveCount(5);
  expect(await sections.evaluateAll((els) => els.map((el) => el.getAttribute("data-alias")))).toEqual(
    DEFAULT_ALIASES,
  );
  // CPU collapses to the 'all' aggregate, like the Streamlit overview
  const cpu = page.locator("[data-testid=chart-card][data-alias=CPU]");
  await expect(cpu).toHaveAttribute("data-device", "all");
  await expect(cpu).toContainText("all of 4");
  await expect(cpu).toContainText("96 samples · 10 metrics");
  await expect(cpu.locator("canvas").first()).toBeVisible();

  // diagram order follows the option order, not the click order: Block
  // Devices is clicked last but sorts first; it has one chart per device
  await page.getByRole("button", { name: "Block Devices", exact: true }).click();
  await expect(sections.first()).toHaveAttribute("data-alias", "Block Devices");
  const blockCards = page.locator("[data-testid=chart-card][data-alias='Block Devices']");
  await expect(blockCards).toHaveCount(2);
  await expect(blockCards.nth(0)).toHaveAttribute("data-device", "nvme0n1");
  await expect(blockCards.nth(1)).toHaveAttribute("data-device", "sda");
  await expect(renderedCharts(page)).toHaveCount(7);

  // metric selection: hide everything but %usr in the CPU chart
  await cpu.getByTestId("metric-filter").click();
  await page.getByRole("menuitem", { name: "Hide all" }).click();
  await expect(cpu.getByTestId("metric-filter")).toContainText("0/10");
  await page.keyboard.press("Escape");

  // time filter is applied by the API: 06:00..12:00 every 15 min = 25 samples
  await page.getByLabel("Start time").fill("06:00:00");
  await page.getByLabel("End time").fill("12:00:00");
  await page.getByTestId("show-diagrams").click();
  await expect(cpu).toContainText("25 samples");
  await expect(renderedCharts(page)).toHaveCount(7);

  // statistics tab (pandas describe() from the API)
  await cpu.getByRole("tab", { name: "Statistics" }).click();
  await expect(cpu.getByTestId("statistics-table")).toContainText("%usr");

  await deleteFile(page, name);

  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login/);
  const response = await page.request.get("/api/v1/files");
  expect(response.status()).toBe(401);
});

test("theme toggle switches light/dark and the charts follow", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await login(page);
  const name = await upload(page, SMALL_FIXTURE, "synthetic-host");
  await page.goto(`/overview?file=${encodeURIComponent(name)}`);
  await page.getByTestId("show-diagrams").click();
  await expect(renderedCharts(page)).toHaveCount(5);
  await expect(page.locator("html")).not.toHaveClass(/dark/);

  await page.getByTestId("theme-toggle").click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  // charts are re-created with the dark theme and render again
  await expect(renderedCharts(page)).toHaveCount(5);
  // the choice survives a reload (next-themes stores it)
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);

  await page.getByTestId("theme-toggle").click();
  await page.getByRole("menuitemradio", { name: "Light" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await deleteFile(page, name);
});

test("wrong password shows an error and sets no session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("login-form").getByRole("alert")).toContainText("Invalid username or password");
  const cookies = await page.context().cookies();
  expect(cookies.find((c) => c.name === "sar_session")).toBeUndefined();
});

test("session cookie is httpOnly and the token never reaches page JavaScript", async ({ page }) => {
  await login(page);
  const cookie = (await page.context().cookies()).find((c) => c.name === "sar_session");
  expect(cookie?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("sar_session");
});
