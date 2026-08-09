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
  await expect(page.getByRole("heading", { name: "New inspection" })).toBeVisible();
  await page.getByRole("button", { name: "Choose files" }).focus();
  await expect(page.getByRole("button", { name: "Choose files" })).toBeFocused();
});
