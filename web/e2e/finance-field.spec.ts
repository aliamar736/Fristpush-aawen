import { expect, test } from "@playwright/test";

import { API, DEMO, apiLogin, authGet, loginAs, randomPhone } from "./helpers";

test("pledge → simulated payment with duplicate webhooks → counted once", async ({ page, request }) => {
  const t = await loginAs(page, request, randomPhone());
  const inis = await (await request.get(`${API}/initiatives/`)).json();
  const ini = inis.results.find((i: { status: string }) => i.status === "active");
  const before = (await (await request.get(`${API}/initiatives/${ini.id}/`)).json()).finance.collected;
  await page.goto(`/initiatives/${ini.id}`);
  await page.getByRole("button", { name: "ساهم ماليًا" }).click();
  await page.getByLabel("المبلغ بالدينار الليبي").fill("75");
  await page.getByRole("radio", { name: /دفع إلكتروني/ }).click();
  await page.getByRole("button", { name: "سجّل التعهد" }).click();
  await expect(page).toHaveURL(/contribute\/simulator\//);
  await expect(page.getByText("لا تُخصم أي أموال")).toBeVisible();
  await page.getByRole("button", { name: "نجاح مع تكرار الإشعار 3 مرات" }).click();
  await expect(page.getByText(/succeeded، duplicate، duplicate/)).toBeVisible();
  const after = (await (await request.get(`${API}/initiatives/${ini.id}/`)).json()).finance.collected;
  expect(Number(after) - Number(before)).toBe(75);
  const pledges = await authGet(request, t.access, "/pledges/");
  expect(pledges.results[0].status).toBe("paid");
  await page.goto("/me?tab=contributions");
  await expect(page.getByText("مدفوع ومؤكد")).toBeVisible();
  await expect(page.getByText("محاكي").first()).toBeVisible();
});

test("field worker attaches completion proof; resident independently verifies", async ({ page, request, browser }) => {
  // set up: a referred + acknowledged + in-progress report assigned to the demo field technician (roads agency)
  const cit = await apiLogin(request, randomPhone());
  const rev = await apiLogin(request, DEMO.reviewer);
  const coord = await apiLogin(request, DEMO.coordinator);
  const cats = await (await request.get(`${API}/categories/`)).json();
  const pothole = cats.results.find((c: { slug: string }) => c.slug === "pothole");
  const H = (tk: string) => ({ Authorization: `Bearer ${tk}` });
  const rep = await (await request.post(`${API}/reports/`, { headers: H(cit.access), data: { category: pothole.id, lat: 32.87, lng: 13.17, client_id: crypto.randomUUID() } })).json();
  for (const to of ["under_review", "verified", "referred"]) await request.post(`${API}/reports/${rep.id}/transition/`, { headers: H(rev.access), data: { to } });
  const users = await (await request.get(`${API}/admin/users/?q=${encodeURIComponent("فني ميداني")}`, { headers: H(coord.access) })).json();
  await request.post(`${API}/reports/${rep.id}/assign/`, { headers: H(coord.access), data: { field_assignee: users.results[0].id } });
  await request.post(`${API}/reports/${rep.id}/transition/`, { headers: H(coord.access), data: { to: "acknowledged", note: "اتصال هاتفي" } });
  await request.post(`${API}/reports/${rep.id}/transition/`, { headers: H(coord.access), data: { to: "in_progress" } });

  await page.setViewportSize({ width: 390, height: 844 });
  await loginAs(page, request, "+218910000014");
  await page.goto("/field");
  await page.getByRole("link", { name: new RegExp(rep.tracking_number) }).click();
  await page.getByRole("button", { name: "أنجزت — أرفق الإثبات" }).click();
  await page.getByLabel("ماذا أُنجز؟").fill("تم ردم الحفرة وتسويتها");
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC", "base64");
  await page.locator('input[type="file"]').setInputFiles({ name: "after.png", mimeType: "image/png", buffer: png });
  await page.getByRole("button", { name: "أرسل الإثبات" }).click();
  await expect(page.locator(".badge").filter({ hasText: "إنجاز بانتظار التحقق" }).first()).toBeVisible();

  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const resident = await ctx.newPage();
  await loginAs(resident, request, randomPhone());
  await resident.goto(`/reports/${rep.id}`);
  await resident.getByRole("button", { name: "هل اتصلحت فعلًا؟ أكّد" }).click();
  await resident.getByRole("radio", { name: "تم الإصلاح" }).click();
  await resident.getByRole("button", { name: "سجّل تحققي" }).click();
  await expect(resident.getByText("سجلنا تحققك")).toBeVisible();
  await ctx.close();
  const res = await request.post(`${API}/reports/${rep.id}/transition/`, { headers: H(rev.access), data: { to: "resolved" } });
  expect(res.status()).toBe(200);
});
