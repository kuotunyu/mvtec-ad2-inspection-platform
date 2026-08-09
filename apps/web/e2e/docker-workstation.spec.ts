import path from "node:path";
import { expect, test } from "@playwright/test";

test.skip(
  process.env.INSPECTION_DOCKER_E2E !== "1",
  "real container workflow runs only through run_system_tests.ps1",
);

test("real container workflow stays inside public response boundaries", async ({ page }) => {
  const failures: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(message.text());
  });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") failures.push(request.url());
  });
  page.on("response", async (response) => {
    const contentType = response.headers()["content-type"] ?? "";
    if (!/(json|text|html)/.test(contentType)) return;
    const body = await response.text().catch(() => "");
    if (/C:\\Users\\|\/Users\/|Traceback \(most recent call last\)/.test(body)) {
      failures.push(`private response content: ${response.url()}`);
    }
  });

  await page.goto("/inspect");
  await page.getByLabel("Inspection files").setInputFiles([
    path.resolve("../../fixtures/public-demo/images/clean-control.png"),
    path.resolve("../../fixtures/public-demo/images/scratch-review.png"),
  ]);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await expect(page.getByText("Inspection completed")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /inspect evidence/i }).first().click();
  await expect(page.getByLabel("Overlay reveal")).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "JSON" }).click();
  await download;

  await page.goto("/review");
  await page.getByRole("button", { name: "Uncertain" }).click();
  await page.getByRole("button", { name: "Confirm uncertain" }).click();
  await expect(page.getByText(/Human decision saved/)).toBeVisible();
  await page.goto("/evidence");
  await expect(page.getByText("Private evaluation: not submitted")).toBeVisible();
  await expect(page.getByText(/detected defect|confirmed defect/i)).toHaveCount(0);
  expect(failures).toEqual([]);
});
