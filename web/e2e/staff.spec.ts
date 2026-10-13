import { expect, test } from "@playwright/test";

import { API, DEMO, apiLogin, loginAs, randomPhone } from "./helpers";

test.use({ viewport: { width: 1366, height: 900 }, isMobile: false, hasTouch: false });

test("reviewer verifies and refers a report; agency acknowledges separately", async ({ page, request, browser }) => {
  const cit = await apiLogin(request, randomPhone());
  const cats = await (await request.get(`${API}/categories/`)).json();
  const garbage = cats.results.find((c: { slug: string }) => c.slug === "garbage");
  // inside the demo «حي الأندلس» area → routed to the cleaning agency
  const rep = await (await request.post(`${API}/reports/`, { headers: { Authorization: `Bearer ${cit.access}` },
    data: { category: garbage.id, lat: 32.875, lng: 13.13, description: "قمامة متراكمة", client_id: crypto.randomUUID() } })).json();

  await loginAs(page, request, DEMO.reviewer);
  await page.goto(`/staff/reports/${rep.id}`);
  for (const [btn, expected] of [["تحت المراجعة", "تحت المراجعة"], ["موثّق", "موثّق"], ["محال للجهة", "محال للجهة"]]) {
    await page.getByRole("button", { name: btn, exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
    await expect(page.locator(".badge").filter({ hasText: expected }).first()).toBeVisible();
  }
  const ctx2 = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const agencyPage = await ctx2.newPage();
  await loginAs(agencyPage, request, DEMO.cleanStaff);
  await agencyPage.goto("/agency");
  await agencyPage.getByRole("link", { name: rep.tracking_number }).click();
  await agencyPage.getByRole("button", { name: "استلام مؤكد", exact: true }).click();
  await agencyPage.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
  await expect(agencyPage.locator(".badge").filter({ hasText: "استلام مؤكد" }).first()).toBeVisible();
  const pub = await (await request.get(`${API}/reports/${rep.id}/`)).json();
  expect(pub.referral.acknowledged_at).not.toBeNull();
  await ctx2.close();
});

test("a citizen cannot open the staff console", async ({ page, request }) => {
  await loginAs(page, request, randomPhone());
  await page.goto("/staff");
  await expect(page.getByText("ليس لديك صلاحية لهذه الصفحة")).toBeVisible();
});
