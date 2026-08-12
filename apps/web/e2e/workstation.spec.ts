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
  await expect(page.getByText("1 筆近期檢測")).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: "建立檢測" }).click();
  await page.getByLabel("檢測影像檔案").setInputFiles({ name: "synthetic.png", mimeType: "image/png", buffer: Buffer.from("synthetic") });
  await page.getByRole("button", { name: "開始檢測" }).click();
  await expect(page.getByText("檢測已完成")).toBeVisible();
  await page.getByRole("button", { name: /查看 .* 的檢測證據/ }).click();
  await expect(page.getByText("僅供視覺化，不代表瑕疵分類")).toBeVisible();
  await page.getByRole("button", { name: "關閉檢測證據" }).click();
  const download = page.waitForEvent("download"); await page.getByRole("link", { name: "JSON" }).click(); await download;
  await page.getByRole("link", { name: "待覆核項目" }).click();
  await page.getByRole("button", { name: "不確定" }).click(); await page.getByRole("button", { name: "確認不確定" }).click();
  await expect(page.getByText(/已儲存 .* 的人工處置/)).toBeVisible();
  await page.getByRole("link", { name: "Model 與證據" }).click();
  await expect(page.getByText("Private evaluation：not submitted")).toBeVisible();
  await expect(page.getByText(/final rejection/i)).toBeVisible();
  await expect(page.getByText(/detected defect|confirmed defect/i)).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});
