import path from "node:path";
import { expect, test } from "@playwright/test";
import { mockBackend } from "./mockBackend";

const output = process.env.DOCS_SCREENSHOT_DIR;
test.skip(!output, "documentation capture runs only through render_docs_assets.py");

const pages = [
  ["dashboard", "/", "檢測作業總覽"],
  ["new-inspection", "/inspect", "建立檢測"],
  ["job-evidence", "/jobs/synthetic-job", "檢測證據"],
  ["review", "/review", "待覆核項目"],
  ["model-evidence", "/evidence", "Model 與證據"],
] as const;

for (const [name, route, heading] of pages) {
  const scope = name === "model-evidence" ? "portfolio" : "synthetic";
  test(`capture ${scope} ${name}`, async ({ page }) => {
    if (!output) return;
    await mockBackend(page, name === "model-evidence" ? "portfolio" : "public-only");
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto(route);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.getByText("Industrial Evidence Workstation")).toBeVisible();
    if (name === "model-evidence") {
      await expect(page.getByText("Private evaluation：NO-GO under lighting shift")).toBeVisible();
      await expect(page.getByText("8/8")).toBeVisible();
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(100);
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  });
}
