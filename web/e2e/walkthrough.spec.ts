import fs from "node:fs";

import { test, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";

import { API, DEMO, apiLogin, randomPhone } from "./helpers";

/* Narrated screen recording of one report's full journey across roles. Run with WALK=1.
   Writes one .webm per scene to ../docs/walkthrough/scenes and scenes.json (joined by scripts/join-walkthrough.sh). */
test.skip(!process.env.WALK, "set WALK=1 to record the walkthrough video");
test.setTimeout(900_000);

const BASE = process.env.E2E_BASE ?? "http://127.0.0.1:4173";
const OUT = "../docs/walkthrough/scenes";
const MOBILE = { width: 390, height: 844 };
const DESKTOP = { width: 1440, height: 900 };
const scenes: { file: string; device: "mobile" | "desktop" }[] = [];

/* Caption bar + click ripple, injected into every page of a recorded context. */
const OVERLAY = `
(() => {
  const css = \`
    #__cap{position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:2147483646;max-width:94%;
      background:rgba(18,63,70,.95);color:#F6F3EC;direction:rtl;text-align:center;pointer-events:none;
      font:600 var(--cap-size,15px)/1.5 "IBM Plex Sans Arabic","Noto Sans Arabic",Tahoma,sans-serif;
      padding:8px 16px;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.25);border-bottom:3px solid #F4B544}
    .__rip{position:fixed;z-index:2147483647;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;
      border:4px solid #F4B544;background:rgba(244,181,68,.25);pointer-events:none;animation:__r .7s ease-out forwards}
    @keyframes __r{from{transform:scale(.4);opacity:1}to{transform:scale(1.6);opacity:0}}\`;
  const draw = () => {
    if (!document.body) return;
    if (!document.getElementById("__capcss")) {
      const s = document.createElement("style"); s.id = "__capcss"; s.textContent = css; document.head.appendChild(s);
    }
    let el = document.getElementById("__cap");
    const t = sessionStorage.getItem("__cap") || "";
    if (!el) { el = document.createElement("div"); el.id = "__cap"; document.body.appendChild(el); }
    if (el.textContent !== t) el.textContent = t;
    el.style.display = t ? "block" : "none";
    document.documentElement.style.setProperty("--cap-size", innerWidth > 700 ? "21px" : "15px");
  };
  addEventListener("pointerdown", (e) => {
    const r = document.createElement("div"); r.className = "__rip";
    r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
    document.body.appendChild(r); setTimeout(() => r.remove(), 800);
  }, true);
  document.addEventListener("DOMContentLoaded", draw);
  setInterval(draw, 200);
})();`;

const pause = (p: Page, ms = 1200) => p.waitForTimeout(ms);

async function caption(page: Page, text: string, hold = 1600) {
  await page.waitForLoadState("networkidle", { timeout: 4000 }).catch(() => {});
  await page.evaluate((t) => sessionStorage.setItem("__cap", t), text);
  await pause(page, hold);
}

async function tap(page: Page, loc: Locator, after = 1000) {
  await loc.scrollIntoViewIfNeeded();
  await loc.hover().catch(() => {});
  await pause(page, 450);
  await loc.click();
  await pause(page, after);
}

async function typeSlow(page: Page, loc: Locator, text: string) {
  await tap(page, loc, 200);
  await loc.pressSequentially(text, { delay: 55 });
  await pause(page, 600);
}

async function card(page: Page, num: string, title: string, sub: string) {
  await page.setContent(`<!doctype html><html lang="ar" dir="rtl"><body style="margin:0;height:100vh;display:flex;flex-direction:column;
    align-items:center;justify-content:center;gap:14px;background:#123F46;color:#F6F3EC;text-align:center;
    font-family:'IBM Plex Sans Arabic','Noto Sans Arabic',Tahoma,sans-serif;padding:0 24px;box-sizing:border-box">
    <div style="font-size:56px;font-weight:700;color:#F4B544">${num}</div>
    <div style="font-size:30px;font-weight:700">${title}</div>
    <div style="font-size:18px;opacity:.85;max-width:720px;line-height:1.6">${sub}</div></body></html>`);
  await pause(page, 3200);
}

async function scene(browser: Browser, name: string, device: "mobile" | "desktop",
  body: (page: Page, ctx: BrowserContext) => Promise<void>) {
  const size = device === "mobile" ? MOBILE : DESKTOP;
  const ctx = await browser.newContext({
    baseURL: BASE, locale: "ar-LY", viewport: size, isMobile: device === "mobile", hasTouch: device === "mobile",
    recordVideo: { dir: `${OUT}/${name}`, size },
  });
  ctx.setDefaultTimeout(15_000);
  await ctx.addInitScript(OVERLAY);
  const page = await ctx.newPage();
  try {
    await body(page, ctx);
  } catch (e) {
    console.log("SCENE FAILED", name, (e as Error).message.split("\n")[0]);
    await page.screenshot({ path: `${OUT}/${name}-failure.png` }).catch(() => {});
  }
  await pause(page, 600);
  const video = page.video();
  await ctx.close();
  if (video) {
    const file = `${OUT}/${name}.webm`;
    fs.renameSync(await video.path(), file);
    fs.rmSync(`${OUT}/${name}`, { recursive: true, force: true });
    scenes.push({ file: `${name}.webm`, device });
  }
}

/* Sign in a context without showing the form again (tokens straight into storage). */
async function signIn(page: Page, phone: string) {
  const r = await page.request.post(`${BASE}${API}/auth/otp/request`, { data: { phone } });
  const { dev_code } = await r.json();
  const t = await (await page.request.post(`${BASE}${API}/auth/otp/verify`, { data: { phone, code: dev_code, display_name: "ساكن" } })).json();
  await page.goto("/login");
  await page.evaluate((tk) => { localStorage.setItem("aawen.tokens", JSON.stringify(tk)); localStorage.setItem("aawen.area", "1"); },
    { access: t.access, refresh: t.refresh });
}

test("report journey walkthrough", async ({ browser, request }) => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  let reportId = 0;
  let tracking = "";

  // ---------- 1. citizen reports a problem (phone)
  await scene(browser, "01-citizen-report", "mobile", async (page) => {
    await card(page, "١", "المواطن يبلّغ عن مشكلة", "حاوية قمامة فايضة في الحومة — من تسجيل الدخول حتى إرسال البلاغ");
    await page.goto("/login");
    await caption(page, "الدخول برقم الهاتف فقط — لا كلمة مرور");
    await typeSlow(page, page.getByLabel("رقم الهاتف"), "0910000012");
    await tap(page, page.getByRole("button", { name: "أرسل رمز الدخول" }));
    await page.getByLabel("رمز الدخول").waitFor();
    await caption(page, "يصل رمز من 6 أرقام برسالة (هنا يظهر على الشاشة لأن الرسائل محاكاة)", 2200);
    const code = (await page.locator('[role="note"] b').innerText()).trim();
    await typeSlow(page, page.getByLabel("رمز الدخول"), code);
    await tap(page, page.getByRole("button", { name: "دخول", exact: true }), 1500);
    await page.evaluate(() => localStorage.setItem("aawen.area", "1"));
    await page.goto("/");
    await caption(page, "«حومتي»: ما يحدث في المنطقة — وزر «بلّغ» في المنتصف", 2600);
    await page.mouse.wheel(0, 500); await pause(page, 1200);
    await page.mouse.wheel(0, -500); await pause(page, 600);

    await caption(page, "نضغط «بلّغ»", 900);
    await tap(page, page.getByRole("link", { name: "بلّغ عن مشكلة" }), 1400);
    await caption(page, "الخطوة 1: مكان المشكلة — نضغط على الخريطة ليظهر الدبوس", 2200);
    const map = page.getByRole("region", { name: "اختيار موقع المشكلة" });
    const b = (await map.boundingBox())!;
    await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await pause(page, 1200);
    await caption(page, "ونكتب معلمًا قريبًا يساعد الفرق على الوصول", 1200);
    await typeSlow(page, page.getByLabel("معلم قريب"), "قدام مخبز النور");
    await tap(page, page.getByRole("button", { name: "التالي" }), 1200);

    await caption(page, "الخطوة 2: نوع المشكلة", 1400);
    await tap(page, page.getByRole("radio", { name: "قمامة" }));
    await caption(page, "نصف المشكلة باختصار", 900);
    await typeSlow(page, page.getByLabel("وصف المشكلة"), "حاوية القمامة فايضة من يومين والريحة قوية");
    await caption(page, "ونرفق صورة (تُضغط تلقائيًا ولا تُنشر قبل مراجعتها)", 1600);
    await page.locator('input[type="file"][accept="image/*"]').first().setInputFiles("e2e/fixtures/overflowing-bin.jpg");
    await pause(page, 1500);
    await page.mouse.wheel(0, 400); await pause(page, 1200);
    await tap(page, page.getByRole("button", { name: "التالي" }), 1200);

    await caption(page, "الخطوة 3: متى رأيتها؟", 1400);
    await tap(page, page.getByRole("button", { name: "اليوم الصبح" }));
    await tap(page, page.getByRole("button", { name: "التالي" }), 1500);

    await caption(page, "الخطوة 4: هل بلّغ أحد عن نفس المشكلة؟ إن وُجدت نؤكدها بدل التكرار", 2600);
    await tap(page, page.getByRole("button", { name: /التالي|بلاغي مختلف/ }), 1300);

    await caption(page, "الخطوة 5: مراجعة أخيرة — هويتك لا تظهر للعامة", 2400);
    await page.mouse.wheel(0, 400); await pause(page, 1000);
    await tap(page, page.getByRole("button", { name: "أرسل البلاغ" }), 2000);
    await page.waitForURL(/\/reports\/\d+/);
    reportId = Number(page.url().match(/reports\/(\d+)/)![1]);
    await caption(page, "وصل البلاغ: رقم متابعة ومسار واضح للخطوات القادمة", 2800);
    await page.mouse.wheel(0, 500); await pause(page, 1800);
    await page.mouse.wheel(0, 500); await pause(page, 1800);
  });

  const coord = await apiLogin(request, DEMO.coordinator);
  const r0 = await (await request.get(`${API}/reports/${reportId}/`, { headers: { Authorization: `Bearer ${coord.access}` } })).json()
    .catch(() => ({}));
  tracking = r0.tracking_number ?? "";
  console.log("REPORT", reportId, tracking, "agency:", r0.agency, r0.agency_name);

  // ---------- 2. AAWEN team reviews and refers (desktop)
  await scene(browser, "02-team-review", "desktop", async (page) => {
    await card(page, "٢", "فريق عاون يراجع ويحيل", "المنسق يتحقق من البلاغ ثم يحيله للجهة المختصة");
    await signIn(page, DEMO.coordinator);
    await page.goto("/staff/queue?queue=review");
    await caption(page, "قائمة المراجعة: البلاغات الجديدة مرتبة حسب الأولوية", 2600);
    const row = page.getByText(tracking).first();
    if (tracking && await row.isVisible().catch(() => false)) await tap(page, row, 1600);
    else await page.goto(`/staff/reports/${reportId}`);
    await caption(page, "منضدة البلاغ: التفاصيل والصورة والأولوية — والمبلّغ ظاهر للفريق فقط", 3000);
    await caption(page, "نبدأ المراجعة", 800);
    await tap(page, page.getByRole("button", { name: "تحت المراجعة", exact: true }));
    await tap(page, page.getByRole("dialog").getByRole("button", { name: "تأكيد" }), 1500);
    await caption(page, "البلاغ صحيح: نوثّقه", 1000);
    await tap(page, page.getByRole("button", { name: "موثّق", exact: true }));
    await tap(page, page.getByRole("dialog").getByRole("button", { name: "تأكيد" }), 1500);
    await caption(page, "نحيله للجهة — الجهة مقترحة تلقائيًا من دليل الاختصاص", 1400);
    await tap(page, page.getByRole("button", { name: "محال للجهة", exact: true }), 1800);
    await tap(page, page.getByRole("dialog").getByRole("button", { name: "تأكيد" }), 1800);
    await caption(page, "أُحيل البلاغ. لن يُغلق حتى تؤكد الجهة الاستلام وتنجز ويتحقق طرف مستقل", 3000);
    await page.mouse.wheel(0, 600); await pause(page, 2000);
  });

  // ---------- 3. citizen sees progress (phone)
  await scene(browser, "03-citizen-progress", "mobile", async (page) => {
    await card(page, "٣", "المواطن يتابع", "كل تغيير في البلاغ يظهر له مباشرة");
    await signIn(page, DEMO.citizen);
    await page.goto(`/reports/${reportId}`);
    await caption(page, "الحالة الآن: محال للجهة — والمسار يوضح ما تم وما بقي", 2800);
    await page.mouse.wheel(0, 500); await pause(page, 2000);
    await page.goto("/notifications");
    await caption(page, "وإشعار بكل تحديث", 2600);
  });

  // ---------- 4. agency receives, works, proves (desktop)
  await scene(browser, "04-agency-fix", "desktop", async (page) => {
    await card(page, "٤", "الجهة المختصة تنفّذ", "موظف جهة النظافة: يؤكد الاستلام، يبدأ العمل، ثم يرفق إثبات الإنجاز");
    await signIn(page, DEMO.cleanStaff);
    await page.goto("/agency");
    await caption(page, "بوابة الجهة: ترى فقط ما أُحيل إليها", 2400);
    const link = page.getByRole("link", { name: tracking });
    if (tracking && await link.isVisible().catch(() => false)) await tap(page, link, 1600);
    else await page.goto(`/staff/reports/${reportId}`);
    await caption(page, "تأكيد الاستلام — خطوة منفصلة يراها المواطن", 1400);
    await tap(page, page.getByRole("button", { name: "استلام مؤكد", exact: true }));
    await tap(page, page.getByRole("dialog").getByRole("button", { name: "تأكيد" }), 1500);
    await caption(page, "بدأ العمل", 900);
    await tap(page, page.getByRole("button", { name: "قيد التنفيذ", exact: true }));
    await tap(page, page.getByRole("dialog").getByRole("button", { name: "تأكيد" }), 1500);
    await caption(page, "انتهى العمل: نرفق ملاحظة وصورة بعد الإنجاز", 1400);
    await tap(page, page.getByRole("button", { name: "أنجزت — أرفق الإثبات" }), 1200);
    const dlg = page.getByRole("dialog");
    await typeSlow(page, dlg.locator("#pn"), "تم تفريغ الحاوية وتنظيف المكان حولها");
    await dlg.locator('input[type="file"]').setInputFiles("e2e/fixtures/clean-bin.jpg");
    await pause(page, 1200);
    await tap(page, dlg.getByRole("button", { name: "أرسل الإثبات" }), 2000);
    await caption(page, "الحالة: إنجاز بانتظار التحقق — الجهة لا تستطيع إغلاق البلاغ بنفسها", 3000);
    await page.mouse.wheel(0, 600); await pause(page, 1800);
  });

  // ---------- 5. a neighbour verifies (phone)
  await scene(browser, "05-neighbour-verifies", "mobile", async (page) => {
    await card(page, "٥", "ساكن آخر يتحقق", "تأكيد مستقل من غير المنفذ: هل اتصلحت فعلًا؟");
    await signIn(page, `0${randomPhone().slice(1)}`);
    await page.goto(`/reports/${reportId}`);
    await caption(page, "يرى الساكن صورة الإنجاز ويُسأل: هل اتصلحت فعلًا؟", 2600);
    await page.mouse.wheel(0, 400); await pause(page, 1400);
    await tap(page, page.getByRole("button", { name: "هل اتصلحت فعلًا؟ أكّد" }), 1200);
    await tap(page, page.getByRole("radio", { name: "تم الإصلاح" }));
    await typeSlow(page, page.locator("#chk"), "مريت اليوم، المكان نظيف");
    await tap(page, page.getByRole("button", { name: "سجّل تحققي" }), 2200);
    await caption(page, "سُجّل التحقق المستقل", 2200);
  });

  // ---------- 6. team closes as resolved (desktop)
  await scene(browser, "06-team-resolves", "desktop", async (page) => {
    await card(page, "٦", "فريق عاون يعتمد الحل", "بعد إثبات المنفذ وتأكيد ساكن مستقل فقط");
    await signIn(page, DEMO.coordinator);
    await page.goto("/staff/queue?queue=verify_done");
    await caption(page, "قائمة «تحقق الإنجاز»", 2200);
    const row = page.getByText(tracking).first();
    if (tracking && await row.isVisible().catch(() => false)) await tap(page, row, 1600);
    else await page.goto(`/staff/reports/${reportId}`);
    await caption(page, "إثبات الجهة + تأكيد الساكن: «تم الإصلاح»", 2400);
    await page.mouse.wheel(0, 500); await pause(page, 1600);
    await page.mouse.wheel(0, -500); await pause(page, 600);
    await tap(page, page.getByRole("button", { name: "محلول", exact: true }), 1400);
    await tap(page, page.getByRole("dialog").getByRole("button", { name: "تأكيد" }), 1800);
    await caption(page, "البلاغ محلول ✓", 2600);
  });

  // ---------- 7. citizen sees it resolved (phone)
  await scene(browser, "07-citizen-resolved", "mobile", async (page) => {
    await card(page, "٧", "النتيجة عند المواطن", "المسار الكامل من البلاغ حتى الحل — مع حق الاعتراض إن رجعت المشكلة");
    await signIn(page, DEMO.citizen);
    await page.goto(`/reports/${reportId}`);
    await caption(page, "محلول: المسار الكامل — من فعل ماذا ومتى", 2600);
    for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, 450); await pause(page, 1500); }
    await caption(page, "وإن رجعت المشكلة: «المشكلة رجعت» أو «أعترض على الإغلاق»", 2800);
    await page.goto("/me?tab=reports");
    await caption(page, "«أثري»: كل بلاغاتي وحالتها", 2800);
  });

  fs.writeFileSync(`${OUT}/scenes.json`, JSON.stringify(scenes, null, 1));
});
