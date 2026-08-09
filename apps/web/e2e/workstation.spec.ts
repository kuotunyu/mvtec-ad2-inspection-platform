import { expect, test } from "@playwright/test";
import { mockBackend } from "./mockBackend";

test("complete synthetic inspection, evidence, review, report, and provenance workflow", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText;
    if (reason !== "net::ERR_ABORTED") browserErrors.push(`${request.method()} ${request.url()}: ${reason}`);
  });
  await mockBackend(page); await page.goto("/");
  await expect(page.getByText("1 recent jobs")).toBeVisible();
  await page.getByRole("link", { name: "＋ New inspection" }).click();
  await page.getByLabel("Inspection files").setInputFiles({ name: "synthetic.png", mimeType: "image/png", buffer: Buffer.from("synthetic") });
  await page.getByRole("button", { name: "Start inspection" }).click();
  await expect(page.getByText("Inspection completed")).toBeVisible();
  await page.getByRole("button", { name: /inspect evidence/i }).click();
  await expect(page.getByText("Visualization only — not defect classification")).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();
  const download = page.waitForEvent("download"); await page.getByRole("link", { name: "JSON" }).click(); await download;
  await page.getByRole("link", { name: /review queue/i }).click();
  await page.getByRole("button", { name: "Uncertain" }).click(); await page.getByRole("button", { name: "Confirm uncertain" }).click();
  await expect(page.getByText(/Human decision saved/)).toBeVisible();
  await page.getByRole("link", { name: /model & evidence/i }).click();
  await expect(page.getByText("Private evaluation: not submitted")).toBeVisible();
  await expect(page.getByText(/final rejection/i)).toBeVisible();
  await expect(page.getByText(/detected defect|confirmed defect/i)).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});
