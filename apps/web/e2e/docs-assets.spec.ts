import path from "node:path";
import { expect, test } from "@playwright/test";
import { mockBackend } from "./mockBackend";

const output = process.env.DOCS_SCREENSHOT_DIR;
test.skip(!output, "documentation capture runs only through render_docs_assets.py");

const pages = [
  ["dashboard", "/", "Operations overview"],
  ["new-inspection", "/inspect", "New inspection"],
  ["job-evidence", "/jobs/synthetic-job", "Inspection evidence"],
  ["review", "/review", "Review queue"],
  ["model-evidence", "/evidence", "Model & evidence"],
] as const;

for (const [name, route, heading] of pages) {
  test(`capture synthetic ${name}`, async ({ page }) => {
    if (!output) return;
    await mockBackend(page);
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto(route);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  });
}
