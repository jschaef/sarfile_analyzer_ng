import { expect, type Page } from "@playwright/test";

export const USER = process.env.SAR_E2E_USER ?? "admin";
export const PASSWORD = process.env.SAR_E2E_PASSWORD ?? "password";

export async function login(page: Page) {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login\?next=%2Foverview/);
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByTestId("current-user")).toHaveText(USER);
}

// Uploads one file on the Files page and returns the name the API gave it.
export async function upload(page: Page, path: string, hostPart: string): Promise<string> {
  await page.getByRole("link", { name: "Manage SAR Files" }).click();
  await expect(page).toHaveURL(/\/files/);
  await page.getByTestId("upload-input").setInputFiles(path);
  await expect(page.getByText(/^Uploaded as /).first()).toBeVisible({ timeout: 90_000 });
  const row = page.getByTestId("file-row").filter({ hasText: hostPart }).first();
  await expect(row).toBeVisible();
  return (await row.getAttribute("data-file")) ?? "";
}

export async function deleteFile(page: Page, name: string) {
  await page.goto("/files");
  const row = page.locator(`[data-testid=file-row][data-file="${name}"]`);
  await row.getByTestId("delete-file").click();
  await row.getByTestId("confirm-delete").click();
  await expect(row).toHaveCount(0);
}

export function renderedCharts(page: Page) {
  return page.locator("[data-testid=echart][data-state=rendered]");
}
