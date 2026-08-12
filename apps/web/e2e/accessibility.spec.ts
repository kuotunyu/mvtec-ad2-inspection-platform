import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockBackend } from "./mockBackend";

for (const path of ["/", "/inspect", "/jobs/synthetic-job", "/review", "/evidence"]) {
  test(`has no serious accessibility violations at ${path}`, async ({ page }) => {
    await mockBackend(page); await page.goto(path);
    await page.locator("main").waitFor();
    const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
    expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))).toEqual([]);
  });
}

test("supports narrow viewport and 200 percent zoom", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await mockBackend(page); await page.goto("/inspect");
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await expect(page.getByRole("heading", { name: "建立檢測" })).toBeVisible();
  await page.getByRole("button", { name: "選擇檔案" }).focus();
  await expect(page.getByRole("button", { name: "選擇檔案" })).toBeFocused();
});

test("review confirmation modal has no serious accessibility violations", async ({ page }) => {
  await mockBackend(page); await page.goto("/review");
  await page.getByRole("button", { name: "拒絕" }).click();
  await expect(page.getByRole("dialog", { name: "確認人工拒絕" })).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))).toEqual([]);
});
