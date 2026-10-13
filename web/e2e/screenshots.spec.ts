import { test } from "@playwright/test";

import { DEMO, loginAs } from "./helpers";

/* Generates the screenshots in docs/screenshots (run with SHOTS=1). Uses demo data; tiles may be blank offline. */
test.skip(!process.env.SHOTS, "set SHOTS=1 to regenerate documentation screenshots");
const OUT = "../docs/screenshots";

test("mobile citizen screens", async ({ page, request }) => {
  await loginAs(page, request, DEMO.citizen);
  await page.evaluate(() => localStorage.setItem("aawen.area", "1"));
  const shots: [string, string][] = [["01-home-hawmati", "/"], ["02-map-layers", "/map"], ["03-report-wizard", "/report/new"],
    ["04-report-detail-path", "/reports/1"], ["05-aawen-initiatives", "/aawen"], ["06-take-a-task", "/aawen?tab=tasks"],
    ["07-goodwill-store", "/aawen?tab=store"], ["08-contribute", "/contribute"], ["09-initiative-transparency", "/initiatives/1"],
    ["10-my-impact", "/me"], ["11-road-alert", "/road/1"], ["12-proposals", "/proposals"]];
  for (const [name, path] of shots) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/${name}.png` });
  }
  await page.goto("/report/new");
  const map = page.getByRole("region", { name: "اختيار موقع المشكلة" });
  const b = (await map.boundingBox())!;
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
  await page.getByRole("button", { name: "التالي" }).click();
  await page.getByRole("radio", { name: "قمامة" }).click();
  await page.getByLabel("وصف المشكلة").fill("حاوية زبالة فايضة، اتصلوا بي 0912345678");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/13-wizard-ai-hint-privacy-warning.png`, fullPage: true });
});

test("desktop consoles", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const run = async (phone: string, list: [string, string][]) => {
    await loginAs(page, request, phone);
    for (const [name, path] of list) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(800);
      await page.screenshot({ path: `${OUT}/${name}.png` });
    }
  };
  await run(DEMO.coordinator, [["20-staff-overview", "/staff"], ["21-staff-queue", "/staff/queue"], ["22-staff-report-workbench", "/staff/reports/6"],
    ["23-media-moderation", "/staff/moderation"], ["24-coverage", "/staff/coverage"], ["25-routing-rules", "/staff/geo"]]);
  await run(DEMO.admin, [["26-settings-road-rules", "/staff/settings"], ["27-users-roles", "/staff/users"], ["28-audit-log", "/staff/audit"]]);
  await run(DEMO.accountant, [["29-finance-ledger", "/staff/finance?tab=ledger"], ["30-finance-reconciliation", "/staff/finance?tab=reconciliation"]]);
  await run(DEMO.cleanStaff, [["31-agency-portal", "/agency?"], ["32-field-tasks", "/field"]]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.screenshot({ path: `${OUT}/33-citizen-desktop.png` });
});
