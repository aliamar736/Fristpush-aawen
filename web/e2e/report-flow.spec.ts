import { expect, test } from "@playwright/test";

import { API, authGet, loginAs, randomPhone } from "./helpers";

async function fillWizard(page: import("@playwright/test").Page, desc: string) {
  await page.goto("/report/new");
  await expect(page.getByRole("heading", { name: "بلّغ عن مشكلة" })).toBeVisible();
  // step 1 — tap the map to drop the pin (map tiles may be unavailable; the map still accepts clicks)
  const map = page.getByRole("region", { name: "اختيار موقع المشكلة" });
  const box = (await map.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.getByLabel("معلم قريب").fill("قدام المخبز");
  await page.getByRole("button", { name: "التالي" }).click();
  // step 2 — category + description
  await page.getByRole("radio", { name: "حفر" }).click();
  await page.getByLabel("وصف المشكلة").fill(desc);
  await page.getByRole("button", { name: "التالي" }).click();
  // step 3 — observed time
  await page.getByRole("button", { name: "قبل ساعة" }).click();
  await page.getByRole("button", { name: "التالي" }).click();
}

test("citizen submits a report through the wizard and lands on its tracking page", async ({ page, request }) => {
  const t = await loginAs(page, request, randomPhone());
  await fillWizard(page, "حفرة عميقة في نص الطريق");
  // step 4 — nearby similar reports (continue with a new report either way)
  await page.getByRole("button", { name: /التالي|بلاغي مختلف/ }).click();
  await page.getByRole("button", { name: "أرسل البلاغ" }).click();
  await expect(page).toHaveURL(/\/reports\/\d+$/);
  await expect(page.getByText(/AW-\d{4}-\d{6}/).first()).toBeVisible();
  await expect(page.getByRole("list", { name: "مسار البلاغ" })).toContainText("مقدّم");
  const mine = await authGet(request, t.access, "/reports/mine/");
  expect(mine.count).toBe(1);
  expect(mine.results[0].observed_at).not.toBe(mine.results[0].submitted_at);
});

test("report written offline is queued, then sent exactly once when the connection returns", async ({ page, request, context }) => {
  const t = await loginAs(page, request, randomPhone());
  await fillWizard(page, "تسرب مية قدام البيت");
  await page.getByRole("button", { name: /التالي|بلاغي مختلف/ }).click();
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByText("أنت غير متصل").first()).toBeVisible();
  await page.getByRole("button", { name: "احفظ للإرسال لاحقًا" }).click();
  await expect(page.getByText("محفوظ وبانتظار الاتصال")).toBeVisible();
  // impatient user taps again — still one draft, one report
  await page.getByRole("button", { name: "احفظ للإرسال لاحقًا" }).click();
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect.poll(async () => (await authGet(request, t.access, "/reports/mine/")).count, { timeout: 20_000 }).toBe(1);
  await page.waitForTimeout(1500);
  expect((await authGet(request, t.access, "/reports/mine/")).count).toBe(1);
});

test("a resident confirms an existing nearby report instead of filing a duplicate", async ({ page, request }) => {
  // someone else files a report at a known spot
  const other = await (async () => { const { apiLogin } = await import("./helpers"); return apiLogin(request, randomPhone()); })();
  const cats = await (await request.get(`${API}/categories/`)).json();
  const pothole = cats.results.find((c: { slug: string }) => c.slug === "pothole");
  const created = await (await request.post(`${API}/reports/`, { headers: { Authorization: `Bearer ${other.access}` },
    data: { category: pothole.id, lat: 32.8872, lng: 13.1913, description: "حفرة", client_id: crypto.randomUUID() } })).json();
  await loginAs(page, request, randomPhone());
  await fillWizard(page, "نفس الحفرة");
  const confirm = page.getByRole("button", { name: "نفس المشكلة، أؤكدها" }).first();
  await expect(confirm).toBeVisible();
  await confirm.click();
  await expect(page).toHaveURL(/\/reports\/\d+$/);
  const confirmedId = page.url().split("/").pop();
  const pub = await (await request.get(`${API}/reports/${confirmedId}/`)).json();
  expect(pub.confirmations_count).toBeGreaterThanOrEqual(1);
  expect(created.id).toBeGreaterThan(0);
});
