import type { APIRequestContext, Page } from "@playwright/test";

export const API = "/api/v1";
export function randomPhone() {
  return "091" + String(Math.floor(1000000 + Math.random() * 8999999));
}

export async function apiLogin(request: APIRequestContext, phone: string) {
  const r = await (await request.post(`${API}/auth/otp/request`, { data: { phone } })).json();
  const t = await (await request.post(`${API}/auth/otp/verify`, { data: { phone, code: r.dev_code, display_name: "اختبار" } })).json();
  return t as { access: string; refresh: string };
}

export async function loginAs(page: Page, request: APIRequestContext, phone: string) {
  const t = await apiLogin(request, phone);
  await page.goto("/login");
  await page.evaluate((tk) => localStorage.setItem("aawen.tokens", JSON.stringify(tk)), { access: t.access, refresh: t.refresh });
  return t;
}

export async function authGet(request: APIRequestContext, token: string, path: string) {
  return (await request.get(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } })).json();
}

export const DEMO = { reviewer: "+218910000002", coordinator: "+218910000003", cleanStaff: "+218910000004", accountant: "+218910000010",
  auditor: "+218910000011", citizen: "+218910000012", admin: "+218910000001" };
