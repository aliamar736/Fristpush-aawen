import fs from "node:fs";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { API, DEMO, apiLogin, loginAs, randomPhone } from "./helpers";

/* Full visual tour of every page / step / dialog. Run with TOUR=1. Writes ../docs/tour/*.png + manifest.json */
test.skip(!process.env.TOUR, "set TOUR=1 to generate the visual tour");
test.describe.configure({ mode: "serial" });
test.setTimeout(600_000);

const OUT = "../docs/tour";
type Shot = { file: string; section: string; title: string; note: string; device: "mobile" | "desktop" };
const manifest: Shot[] = [];
let n = 0;

async function shot(page: Page, section: string, title: string, note: string, opts: { full?: boolean } = {}) {
  n += 1;
  const file = `${String(n).padStart(3, "0")}.png`;
  const device = (page.viewportSize()?.width ?? 0) > 700 ? "desktop" : "mobile";
  try {
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(500);
    if (opts.full) await page.addStyleTag({ content: ".tabbar{display:none !important} .topbar{position:static !important}" });
    await page.screenshot({ path: `${OUT}/${file}`, fullPage: !!opts.full });
    if (opts.full) await page.addStyleTag({ content: ".tabbar{display:grid !important} .topbar{position:sticky !important}" });
    manifest.push({ file, section, title, note, device });
  } catch (e) {
    console.log("SHOT FAILED", title, (e as Error).message);
  }
}

async function safe(label: string, fn: () => Promise<void>) {
  try {
    await fn();
  } catch (e) {
    console.log("STEP FAILED", label, (e as Error).message.split("\n")[0]);
  }
}

const H = (t: string) => ({ Authorization: `Bearer ${t}` });

async function catId(request: APIRequestContext, slug: string) {
  const c = await (await request.get(`${API}/categories/`)).json();
  return c.results.find((x: { slug: string }) => x.slug === slug).id as number;
}

test.beforeAll(() => fs.mkdirSync(OUT, { recursive: true }));
test.afterAll(() => fs.writeFileSync(`${OUT}/manifest.json`, JSON.stringify(manifest, null, 1)));

test("citizen app (mobile)", async ({ page, request, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const S = "المواطن";

  // ---- signed-out first look
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
  await page.goto("/");
  await shot(page, S, "حومتي — قبل اختيار المنطقة", "أول ما يراه الزائر دون حساب: اختيار الحومة أو تحديدها بالموقع.");
  await page.goto("/login");
  await shot(page, S, "الدخول — رقم الهاتف", "التصفح دون حساب؛ الرقم مطلوب فقط عند الإرسال أو الحجز أو المساهمة.");
  await safe("login code", async () => {
    await page.getByLabel("رقم الهاتف").fill("0915551234");
    await page.getByRole("button", { name: "أرسل رمز الدخول" }).click();
    await page.getByLabel("رمز الدخول").waitFor();
    await shot(page, S, "الدخول — رمز التحقق", "في بيئة التطوير يظهر الرمز لأن الرسائل تعمل بمحاكٍ.");
  });
  await page.goto("/login");
  await page.getByRole("tab", { name: "كلمة مرور (للفرق)" }).click();
  await shot(page, S, "الدخول — كلمة مرور للفرق", "خيار لأعضاء الفرق الذين وضعوا كلمة مرور بأنفسهم.");

  // ---- signed in as the demo citizen
  await loginAs(page, request, DEMO.citizen);
  await page.evaluate(() => localStorage.setItem("aawen.area", "1"));
  await page.goto("/");
  await shot(page, S, "حومتي — الواجهة الرئيسية", "التبويبات الخمسة وزر «بلّغ» في المنتصف.");
  await shot(page, S, "حومتي — الصفحة كاملة", "ملخص البلاغات، تنبيهات الجهات، المبادرات، ما اتحل، اقتراحات السكان، دليل الخدمات الموثق.", { full: true });

  // ---- map
  await page.goto("/map");
  await shot(page, S, "الخريطة — الطبقات", "طبقات مستقلة وتجميع العلامات عند التصغير. (خلفية الشوارع لا تظهر في بيئة الالتقاط فقط.)");
  await safe("map filters", async () => {
    await page.getByRole("button", { name: "فلاتر" }).click();
    await shot(page, S, "الخريطة — الفلاتر", "الفئة، الحالة، الفترة، وأنواع تنبيهات الطريق.");
    await page.getByRole("button", { name: "تم" }).click();
  });
  await safe("map select", async () => {
    await page.locator(".leaflet-marker-icon .pin").first().click({ force: true });
    await page.waitForTimeout(400);
    await shot(page, S, "الخريطة — تفاصيل علامة", "بطاقة مختصرة مع رابط البلاغ وملف المكان.");
  });

  // ---- report wizard
  await page.goto("/report/new");
  await shot(page, S, "بلّغ — 1. المكان", "تنبيه أن البلاغ ليس طلب نجدة، ثم تحديد المكان على الخريطة أو بالموقع اللحظي.");
  await safe("wizard", async () => {
    const map = page.getByRole("region", { name: "اختيار موقع المشكلة" });
    const b = (await map.boundingBox())!;
    await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await page.getByLabel("معلم قريب").fill("قدام مخبز النور");
    await shot(page, S, "بلّغ — 1. الدبوس والمعلم القريب", "الدبوس الأصفر قابل للسحب، ومعلم قريب يكتبه المبلّغ أو يختاره.", { full: true });
    await page.getByRole("button", { name: "التالي" }).click();
    await shot(page, S, "بلّغ — 2. نوع المشكلة", "فئات البداية (قابلة للزيادة من الإدارة).");
    await page.getByRole("radio", { name: "قمامة" }).click();
    await page.getByLabel("وصف المشكلة").fill("حاوية زبالة فايضة من يومين، اتصلوا بي 0912345678");
    await page.waitForTimeout(1600);
    await page.locator('input[type="file"][accept="image/*"]').setInputFiles("e2e/fixtures/overflowing-bin.jpg");
    await page.waitForTimeout(600);
    await shot(page, S, "بلّغ — 2. الوصف والصورة والتنبيه للخصوصية", "اقتراح الفئة الذكي (اختياري) وتحذير عند كتابة رقم هاتف أو اسم؛ صورة مضغوطة؛ تسجيل صوتي؛ درجة الخطر.", { full: true });
    await page.getByRole("button", { name: "التالي" }).click();
    await page.getByRole("button", { name: "اليوم الصبح" }).click();
    await shot(page, S, "بلّغ — 3. وقت الرصد", "وقت رؤية المشكلة منفصل عن وقت الإرسال.");
    await page.getByRole("button", { name: "التالي" }).click();
    await page.waitForTimeout(800);
    await shot(page, S, "بلّغ — 4. بلاغات قريبة", "إن كانت نفس المشكلة يؤكدها بدل إرسال بلاغ مكرر.", { full: true });
    await page.getByRole("button", { name: /التالي|بلاغي مختلف/ }).click();
    await shot(page, S, "بلّغ — 5. المراجعة والإرسال", "ملخص قبل الإرسال؛ الهوية لا تظهر للعامة.");
    await context.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event("offline")));
    await page.getByRole("button", { name: "احفظ للإرسال لاحقًا" }).click();
    await page.getByText("محفوظ وبانتظار الاتصال").waitFor();
    await shot(page, S, "بلّغ — دون اتصال", "يُحفظ البلاغ على الجهاز ويُرسل تلقائيًا عند عودة الاتصال، دون تكرار.");
    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await page.waitForTimeout(3500);
  });

  // ---- report detail states
  const cit = await apiLogin(request, DEMO.citizen);
  const rev = await apiLogin(request, DEMO.reviewer);
  const mine = await (await request.get(`${API}/reports/mine/`, { headers: H(cit.access) })).json();
  const newest = mine.results[0];
  await page.goto(`/reports/${newest.id}`);
  await shot(page, S, "تفاصيل البلاغ — بعد الإرسال", "رقم المتابعة ومسار المعالجة: الخطوات القادمة بخط منقط.", { full: true });
  await safe("needs info", async () => {
    for (const to of ["under_review"]) await request.post(`${API}/reports/${newest.id}/transition/`, { headers: H(rev.access), data: { to } });
    await request.post(`${API}/reports/${newest.id}/transition/`, { headers: H(rev.access), data: { to: "needs_info", reason: "هل الحاوية على الرصيف أم في الشارع؟" } });
    await page.goto(`/reports/${newest.id}`);
    await shot(page, S, "تفاصيل البلاغ — يحتاج معلومات", "سؤال فريق المراجعة يظهر للمبلّغ مع زر لإضافة المعلومة.");
    await page.getByRole("button", { name: "أضف المعلومات" }).click();
    await shot(page, S, "إضافة معلومات", "يرد المبلّغ فيعود البلاغ للمراجعة.");
  });
  await page.goto("/reports/1");
  await shot(page, S, "بلاغ محلول — المسار الكامل", "من التقديم حتى الحل مع الإحالة واستلام الجهة والتأكيد المستقل.", { full: true });
  await safe("object dialog", async () => {
    await page.getByRole("button", { name: "أعترض على الإغلاق" }).click();
    await shot(page, S, "الاعتراض على الإغلاق", "يُراجع الاعتراض من فريق مستقل.");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "المشكلة رجعت" }).click();
    await shot(page, S, "المشكلة رجعت", "إعادة فتح مرتبطة بالإصلاح السابق وتتطلب صورة حديثة.");
    await page.keyboard.press("Escape");
  });
  await safe("done pending", async () => {
    const r = mine.results.find((x: { status: string }) => x.status === "done_pending_verification");
    const all = await (await request.get(`${API}/reports/?status=done_pending_verification`)).json();
    const target = r ?? all.results[0];
    const other = await loginAs(page, request, randomPhone());
    void other;
    await page.goto(`/reports/${target.id}`);
    await shot(page, S, "إنجاز بانتظار التحقق", "أي ساكن (غير المنفذ) يؤكد هل اتصلحت فعلًا.");
    await page.getByRole("button", { name: "هل اتصلحت فعلًا؟ أكّد" }).click();
    await shot(page, S, "التحقق المستقل", "تم الإصلاح / جزئي / لم يُصلح، مع صورة اختيارية.");
    await page.keyboard.press("Escape");
  });
  await loginAs(page, request, DEMO.citizen);
  await page.evaluate(() => localStorage.setItem("aawen.area", "1"));
  await page.goto("/place?lat=32.8752&lng=13.1255");
  await shot(page, S, "ملف المكان", "كل ما سُجّل حول نقطة: البلاغات، مرات الرجوع، الأعمال المرتبطة.", { full: true });

  // ---- road now
  await page.goto("/road/new");
  await shot(page, S, "تنبيه طريق جديد", "حادث / إغلاق / عائق / ازدحام مبلّغ عنه — مع فصل واضح عن النجدة.", { full: true });
  await page.goto("/road/1");
  await shot(page, S, "تنبيه طريق — ما زال موجود؟", "المصدر، مستوى التحقق، آخر تأكيد، الصلاحية، وأزرار التحديث.", { full: true });

  // ---- Aawen tab
  await page.goto("/aawen");
  await shot(page, S, "عاون — المبادرات و«شن ناقص؟»", "ما يعطّل المبادرات المعتمدة، ثم قائمة المبادرات.", { full: true });
  await safe("new initiative", async () => {
    await page.getByRole("button", { name: "اقترح مبادرة" }).click();
    await shot(page, S, "اقتراح مبادرة", "تُرسل للاعتماد قبل نشرها واستقبال أي مساهمة.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/aawen?tab=tasks");
  await shot(page, S, "خُذ مهمة", "مهام بوقت ومكان ومهارة وعدد مشاركين، ومقترحة حسب «مهاراتي».", { full: true });
  await page.goto("/aawen?tab=skills");
  await shot(page, S, "مهاراتي", "المهارات وأيام وأوقات التوفر والمناطق المفضلة.", { full: true });
  await page.goto("/aawen?tab=store");
  await shot(page, S, "مخزن الخير", "متاح / محجوز / مُعار أو مُسلّم، ومسؤول الاستلام.", { full: true });
  await safe("reserve", async () => {
    await page.getByRole("button", { name: "احجز" }).first().click();
    await shot(page, S, "حجز من مخزن الخير", "الكمية والغرض؛ التسليم يؤكده مسؤول الاستلام.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/aawen?tab=care");
  await shot(page, S, "نقاط العناية", "جهات استضافة موثقة مع خدماتها ومواعيدها وتاريخ التحقق.");
  await page.goto("/aawen?tab=surplus");
  await shot(page, S, "فائض ينفع", "مشاركة الأغذية معطلة حتى تجهيز شريك وإجراءات سلامة.", { full: true });

  // ---- initiative & contribute
  await page.goto("/initiatives/1");
  await shot(page, S, "صفحة المبادرة", "الاحتياجات، التمويل المؤكد مقابل التعهدات، سجل المصروفات ونتائجها، المهام.", { full: true });
  await safe("pledge", async () => {
    await page.getByRole("button", { name: "ساهم ماليًا" }).click();
    await page.getByLabel("المبلغ بالدينار الليبي").fill("50");
    await shot(page, S, "التعهد المالي", "التعهد ليس دفعة؛ وضع الدفع ظاهر بوضوح (محاكاة هنا).");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "عندي هذا" }).first().click();
    await shot(page, S, "عرض مساعدة عينية", "يصل لمسؤول المبادرة: قبول وحجز ثم تسجيل الاستلام.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/contribute");
  await shot(page, S, "ساهم", "احتياجات المشاريع، مساهمات الشركات، والسياسات.", { full: true });
  await safe("simulator", async () => {
    const pl = await (await request.post(`${API}/pledges/`, { headers: H(cit.access), data: { initiative: 1, amount: "40", method: "online", client_id: crypto.randomUUID() } })).json();
    const pay = await (await request.post(`${API}/pledges/${pl.id}/pay/`, { headers: H(cit.access) })).json();
    await page.goto(`/contribute/simulator/${pay.provider_payment_id}`);
    await shot(page, S, "محاكي الدفع", "صفحة تطوير فقط: نجاح، نجاح مع إشعارات مكررة، أو فشل.");
    await page.getByRole("button", { name: "نجاح مع تكرار الإشعار 3 مرات" }).click();
    await page.getByText(/succeeded/).waitFor();
    await shot(page, S, "نتيجة المحاكي", "ثلاثة إشعارات من المزود ← تسجيل الدفعة مرة واحدة فقط.");
  });

  // ---- impact
  for (const [tab, title, note] of [
    ["reports", "أثري — بلاغاتي", "ملخص المشاركة وحالة كل بلاغ."],
    ["drafts", "أثري — المسودات", "مسودات محفوظة على هذا الجهاز."],
    ["tasks", "أثري — مهامي", "حجوزات المهام وإثبات الإتمام بعد تأكيد الحضور."],
    ["contributions", "أثري — مساهماتي", "التعهدات والدفعات والإيصالات وعروض المساعدة."],
    ["store", "أثري — حجوزاتي", "حجوزات مخزن الخير ومواعيد الإرجاع."],
    ["objections", "أثري — اعتراضاتي", "الاعتراضات وقرارات المراجعة."],
    ["account", "أثري — حسابي", "اللغة، الأجهزة المسجلة، حذف الحساب."],
  ] as const) {
    await page.goto(`/me?tab=${tab}`);
    await shot(page, S, title, note, { full: true });
  }
  await page.goto("/notifications");
  await shot(page, S, "الإشعارات", "تحديثات البلاغات والمساهمات والمهام.", { full: true });
  await page.goto("/proposals");
  await shot(page, S, "اقتراحات الحومة والتصويت", "تصويت على المؤهل فقط وضمن الميزانية المعلنة.", { full: true });
  await safe("new proposal", async () => {
    await page.getByRole("button", { name: "اقترح" }).click();
    await shot(page, S, "اقتراح جديد", "يمر بمراجعة الجدوى والإذن والتكلفة والصيانة.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/");
  await page.getByRole("button", { name: "English" }).click();
  await shot(page, S, "English mode", "الواجهة بالإنجليزية واتجاه من اليسار لليمين.");
  await page.getByRole("button", { name: "العربية" }).click();
  await page.goto("/no-such-page");
  await shot(page, S, "صفحة غير موجودة", "حالة الخطأ برسالة واضحة.");
});

test("staff console (desktop)", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const cit = await apiLogin(request, randomPhone());
  const rev = await apiLogin(request, DEMO.reviewer);
  const coord = await apiLogin(request, DEMO.coordinator);

  // --- prepare states: a submitted report with a pending photo of a possible accident; an open objection
  const garbage = await catId(request, "garbage");
  const up = await request.post(`${API}/media/`, { headers: H(cit.access), multipart: { kind: "image", context: "accident",
    file: { name: "a.jpg", mimeType: "image/jpeg", buffer: fs.readFileSync("e2e/fixtures/street-pothole.jpg") } } });
  const media = (await up.json()).uid;
  const rep = await (await request.post(`${API}/reports/`, { headers: H(cit.access), data: { category: garbage, lat: 32.875, lng: 13.13, description: "قمامة متراكمة بجانب المدرسة", media: [media], client_id: crypto.randomUUID(), danger_level: 2 } })).json();
  await safe("objection", async () => {
    const res = await (await request.get(`${API}/reports/?status=resolved`)).json();
    const other = await apiLogin(request, randomPhone());
    await request.post(`${API}/reports/${res.results[0].id}/object/`, { headers: H(other.access), data: { reason: "الحفرة ما زالت تتجمع فيها المياه" } });
  });

  const S = "فريق عاون (المراجعة والتنسيق)";
  await loginAs(page, request, DEMO.coordinator);
  await page.goto("/staff");
  await shot(page, S, "نظرة عامة", "قوائم العمل حسب ما يحتاج إجراء، وتوزيع الفئات.");
  for (const [q, t, note] of [["review", "قائمة المراجعة", "بلاغات جديدة أو معاد فتحها، مرتبة بالأولوية."],
    ["routing", "قرارات التوجيه", "حالات حدودية أو خارج التغطية أو بلا قاعدة اختصاص."],
    ["to_refer", "جاهزة للإحالة", "بلاغات موثقة تنتظر الإحالة للجهة."],
    ["verify_done", "تحقق الإنجاز", "إثبات المنفذ بانتظار تأكيد مستقل."],
    ["disputed", "الاعتراضات", "قبول الاعتراض يعيد الفتح، ورفضه يحتاج تعليلًا."],
    ["stale", "إحالات متأخرة", "لم تؤكد الجهة الاستلام — لا تُغلق بل تُصعّد للمنسق."]] as const) {
    await page.goto(`/staff/queue?queue=${q}`);
    await shot(page, S, t, note);
  }
  await page.goto(`/staff/reports/${rep.id}`);
  await shot(page, S, "منضدة البلاغ", "الإجراءات المتاحة لدورك فقط، التفاصيل الداخلية، مكونات الأولوية، المبلّغ (غير ظاهر للعامة)، الوسائط.");
  await safe("transition dialog", async () => {
    await page.getByRole("button", { name: "تحت المراجعة", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "يحتاج معلومات", exact: true }).click();
    await shot(page, S, "طلب معلومات من المبلّغ", "السؤال إلزامي ويظهر للمبلّغ.");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "موثّق", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "محال للجهة", exact: true }).click();
    await shot(page, S, "الإحالة للجهة", "الجهة مقترحة من دليل الاختصاص وتُعدّل في الحالات الحدودية.");
    await page.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "تعيين فريق ميداني / مسؤول متابعة" }).click();
    await page.getByLabel("ابحث عن مستخدم بالاسم أو الهاتف").fill("فني");
    await page.waitForTimeout(800);
    await shot(page, S, "تعيين فريق ميداني ومسؤول متابعة", "كل بلاغ له مسؤول متابعة.");
    await page.keyboard.press("Escape");
    await shot(page, S, "منضدة البلاغ بعد الإحالة", "المسار يُظهر الإحالة؛ الاستلام خطوة منفصلة للجهة.", { full: true });
  });
  await page.goto("/staff/moderation");
  await safe("blur", async () => {
    const img = page.locator(".blur-canvas").first();
    const b = (await img.boundingBox())!;
    await page.mouse.move(b.x + b.width * 0.3, b.y + b.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width * 0.7, b.y + b.height * 0.6, { steps: 5 });
    await page.mouse.up();
  });
  await shot(page, S, "مراجعة الوسائط والطمس", "لا يُنشر شيء قبل المراجعة؛ تحديد مناطق الطمس بالسحب، وتنبيه احتمال وجود مصاب.");
  await page.goto("/staff/followups?status=pending");
  await shot(page, S, "المراجعات اللاحقة", "بعد مدة من الحل: الحل مستمر أم المشكلة رجعت.");
  await page.goto("/staff/bundles");
  await shot(page, S, "حزم الحل", "تجميع بلاغات متقاربة في زيارة، مع بقاء حالة كل بلاغ.");
  await safe("bundle dialog", async () => {
    await page.getByRole("button", { name: "حزمة جديدة" }).click();
    await page.getByLabel("المنطقة").selectOption({ index: 1 });
    await page.waitForTimeout(800);
    await shot(page, S, "إنشاء حزمة", "اختيار المنطقة والبلاغات والموعد.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/staff/initiatives");
  await shot(page, S, "اعتماد المبادرات", "منسق غير مسؤول المبادرة يعتمد أو يعيد للتعديل.");
  await page.goto("/staff/proposals");
  await shot(page, S, "مراجعة اقتراحات الحومة", "الجدوى، الإذن، التكلفة، خطة الصيانة.");
  await safe("proposal review", async () => {
    await page.getByRole("button", { name: "راجع" }).last().click();
    await shot(page, S, "نافذة مراجعة الاقتراح", "لا يُؤهَّل للتصويت قبل اكتمال الفحوص.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/staff/coverage");
  await shot(page, S, "تغطية المناطق الأقل مشاركة", "كشف نقص البيانات وتكليف السفراء بمسح ميداني.");
  await safe("survey", async () => {
    await page.getByRole("button", { name: "كلّف سفيرًا بمسح" }).first().click();
    await page.waitForTimeout(600);
    await shot(page, S, "تكليف مسح ميداني", "اختيار السفير والتعليمات.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/staff/directory");
  await shot(page, S, "الدليل ونقاط العناية", "تسجيل تاريخ التحقق وإخفاء المدخلات غير الصالحة.");
  await page.goto("/staff/categories");
  await shot(page, S, "الفئات", "إضافة فئات وتعديل الخطورة ومدة المراجعة اللاحقة والكلمات المفتاحية.");
  await safe("cat edit", async () => {
    await page.getByRole("button", { name: "تعديل" }).first().click();
    await shot(page, S, "تعديل فئة", "الطبقة، الخطورة، الكلمات المفتاحية للاقتراح الآلي.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/staff/geo");
  await shot(page, S, "المناطق والجهات وقواعد التوجيه", "المنطقة × الفئة ← الجهة.", { full: true });
  await safe("rule", async () => {
    await page.getByRole("button", { name: "قاعدة جديدة" }).click();
    await shot(page, S, "قاعدة اختصاص جديدة", "قاعدة منطقة تتقدم على قاعدة المدينة.");
    await page.keyboard.press("Escape");
  });

  const A = "مدير النظام";
  await loginAs(page, request, DEMO.admin);
  await page.goto("/staff/users");
  await shot(page, A, "المستخدمون والأدوار", "لا كلمات مرور افتراضية؛ الأدوار بنطاق منطقة أو جهة.");
  await safe("grant", async () => {
    await page.getByRole("button", { name: "امنح دورًا" }).first().click();
    await page.locator("#gr").selectOption("agency_staff");
    await shot(page, A, "منح دور", "موظف الجهة يجب ربطه بجهة؛ كل منح مسجّل.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/staff/settings");
  await shot(page, A, "الإعدادات", "قواعد صلاحية تنبيهات الطريق، التوجيه، المراجعة اللاحقة، التصعيد، المزايا، أرقام الطوارئ.", { full: true });
  await page.goto("/staff/audit");
  await shot(page, A, "سجل التغييرات الحساسة", "سجل إضافي فقط ومحمي في قاعدة البيانات.");

  // --- finance: create a pending transfer proof, a requested disbursement and a requested refund
  const F = "المالية (المحاسب والمراجع المالي)";
  const acc = await apiLogin(request, DEMO.accountant);
  const mgr = await apiLogin(request, "+218910000009");
  await safe("finance setup", async () => {
    const p = await (await request.post(`${API}/pledges/`, { headers: H(cit.access), data: { initiative: 1, amount: "300", method: "bank_transfer", client_id: crypto.randomUUID() } })).json();
    const m = await (await request.post(`${API}/media/`, { headers: H(cit.access), multipart: { kind: "document", file: { name: "r.png", mimeType: "image/png", buffer: fs.readFileSync("../brand/png/app-icon-light-512.png") } } })).json();
    await request.post(`${API}/pledges/${p.id}/transfer-proof/`, { headers: H(cit.access), data: { media: m.uid, claimed_reference: "TRX-88412" } });
    await request.post(`${API}/finance/disbursements/`, { headers: H(mgr.access), data: { initiative: 1, amount: "20", purpose: "شراء أكياس قمامة", payee_name: "محل الأمانة" } });
    const pays = await (await request.get(`${API}/finance/payments/`, { headers: H(acc.access) })).json();
    const ok = pays.results.find((x: { status: string }) => x.status === "succeeded");
    if (ok) await request.post(`${API}/finance/refunds/`, { headers: H(acc.access), data: { payment: ok.id, amount: "5", reason: "طلب المساهم" } });
  });
  await loginAs(page, request, DEMO.accountant);
  for (const [tab, t, note] of [["transfers", "مطابقة التحويلات", "صورة الإيصال ليست دفعة حتى تُطابق مع كشف الحساب."],
    ["disbursements", "طلبات الصرف", "الطلب ← اعتماد المراجع المالي ← تنفيذ المحاسب مع إيصال."],
    ["refunds", "الاسترداد", "طلب المحاسب ← اعتماد المراجع المالي ← تأكيد المزود."],
    ["payments", "الدفعات", "كل دفعة بإيصال، والمحاكاة معلّمة."],
    ["ledger", "السجل المالي", "تحصيل/رسوم/صرف/استرداد — غير قابل للتعديل، وتصدير CSV."],
    ["reconciliation", "المطابقة العامة", "مطابقة السجل مع الدفعات المؤكدة وكشف الفروقات والإشعارات المكررة."]] as const) {
    await page.goto(`/staff/finance?tab=${tab}`);
    await shot(page, F, t, note);
  }
  await safe("match", async () => {
    await page.goto("/staff/finance?tab=transfers");
    await page.getByRole("button", { name: "طابق" }).first().click();
    await shot(page, F, "نافذة المطابقة", "رقم العملية في الكشف والمبلغ الوارد فعلًا.");
    await page.keyboard.press("Escape");
  });
  await loginAs(page, request, DEMO.auditor);
  await page.goto("/staff/finance?tab=disbursements");
  await shot(page, F, "المراجع المالي يعتمد الصرف", "لا يعتمد من طلب، ولا ينفّذ من اعتمد.");

  // --- agency portal & field
  const G = "بوابة الجهات والواجهة الميدانية";
  await loginAs(page, request, DEMO.cleanStaff);
  await page.goto("/agency");
  await shot(page, G, "بوابة الجهة — بانتظار تأكيد الاستلام", "ترى الجهة ما أُحيل إليها فقط.");
  await safe("ack", async () => {
    await page.getByRole("link", { name: rep.tracking_number }).click();
    await page.getByRole("button", { name: "استلام مؤكد", exact: true }).click();
    await shot(page, G, "تأكيد الاستلام", "خطوة منفصلة عن الإحالة ويراها المواطن.");
    await page.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "قيد التنفيذ", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "تأكيد" }).click();
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "أنجزت — أرفق الإثبات" }).click();
    await shot(page, G, "إثبات الإنجاز", "ملاحظة وصور بعد الإنجاز — ثم ينتظر تأكيدًا مستقلًا.");
    await page.keyboard.press("Escape");
  });
  await page.goto("/agency?");
  await page.getByRole("tab", { name: "قيد العمل" }).click();
  await shot(page, G, "بوابة الجهة — قيد العمل", "متابعة العمل حسب الحالة.");
  await page.goto("/agency/announcements");
  await shot(page, G, "تنبيهات الجهة للسكان", "انقطاعات وأعمال مجدولة تظهر في «حومتي».");
  await safe("announce", async () => {
    await page.getByRole("button", { name: "تنبيه جديد" }).click();
    await shot(page, G, "تنبيه جديد", "العنوان والتفاصيل والمناطق ومدة العرض.");
    await page.keyboard.press("Escape");
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAs(page, request, "+218910000014");
  await page.goto("/field");
  await shot(page, G, "الواجهة الميدانية (هاتف)", "المهام المسندة للفني مع رابط الموقع.");
  void coord; void rev; void expect;
});
