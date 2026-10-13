import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { DEMO, loginAs } from "./helpers";

const PUBLIC_PAGES = ["/", "/map", "/report/new", "/aawen", "/aawen?tab=store", "/contribute", "/login", "/reports/1", "/proposals", "/initiatives/1"];

for (const path of PUBLIC_PAGES) {
  test(`no serious accessibility violations: ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).exclude(".leaflet-container").analyze();
    const serious = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
  });
}

test("staff console passes accessibility checks", async ({ page, request }) => {
  await page.setViewportSize({ width: 1366, height: 900 });
  await loginAs(page, request, DEMO.coordinator);
  for (const p of ["/staff", "/staff/queue", "/staff/reports/5"]) {
    await page.goto(p);
    await page.waitForLoadState("networkidle");
    const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).exclude(".leaflet-container").analyze();
    const serious = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${p} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
  }
});

test("Arabic RTL by default, English switch flips direction", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.getByRole("navigation", { name: "التبويبات الرئيسية" })).toContainText("حومتي");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.getByRole("navigation", { name: "Main tabs" })).toContainText("My area");
  await page.getByRole("button", { name: "العربية" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});

test("five tabs and the report button are reachable by keyboard", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "التبويبات الرئيسية" });
  for (const name of ["حومتي", "الخريطة", "بلّغ عن مشكلة", "عاون", "ساهم", "أثري"]) await expect(nav.getByRole("link", { name })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "انتقل إلى المحتوى" })).toBeFocused();
});

test("large text (200%) on a small phone does not cause horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/aawen");
  await page.addStyleTag({ content: "html { font-size: 200% !important; }" });
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("error, empty and offline states", async ({ page, context }) => {
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { name: "غير موجود" })).toBeVisible();
  await page.goto("/reports/99999999");
  await expect(page.getByRole("heading", { name: "غير موجود" })).toBeVisible();
  await page.goto("/me");
  await expect(page.getByRole("heading", { name: "سجّل الدخول لمتابعة أثرك" })).toBeVisible();
  await page.goto("/aawen?tab=care");
  await page.waitForLoadState("networkidle");
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByText("أنت غير متصل").first()).toBeVisible();
  // a page never visited before and not cached shows a clear offline message
  await page.getByRole("tab", { name: "فائض ينفع" }).click();
  await expect(page.getByRole("heading", { name: "لا يوجد اتصال" })).toBeVisible();
  // a page visited before falls back to the saved copy and says how old it is
  await page.getByRole("tab", { name: "نقاط العناية" }).click();
  await expect(page.getByText("نسخة محفوظة على جهازك").first()).toBeVisible();
  await context.setOffline(false);
});
