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
  await page.getByLabel("檢測影像檔案").setInputFiles([
    path.resolve("../../fixtures/public-demo/images/clean-control.png"),
    path.resolve("../../fixtures/public-demo/images/scratch-review.png"),
  ]);
  await page.getByRole("button", { name: "開始檢測" }).click();
  await expect(page.getByText("檢測已完成")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /查看 .* 的檢測證據/ }).first().click();
  await expect(page.getByLabel("Overlay 顯示比例")).toBeVisible();
  await page.getByRole("button", { name: "關閉檢測證據" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "JSON" }).click();
  await download;

  await page.goto("/review");
  await page.getByRole("button", { name: "不確定" }).click();
  await page.getByRole("button", { name: "確認不確定" }).click();
  await expect(page.getByText(/已儲存 .* 的人工處置/)).toBeVisible();
  await page.goto("/evidence");
  await expect(page.getByText("Private evaluation：NO-GO under lighting shift")).toBeVisible();
  await expect(page.getByText(/detected defect|confirmed defect/i)).toHaveCount(0);
  expect(failures).toEqual([]);
});
