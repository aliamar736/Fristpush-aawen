# الخدمات الخارجية: ما يعمل وما ينتظر حسابات ومفاتيح

| الخدمة | الحالة الآن | ما يلزم لتفعيلها | المتغيرات |
|---|---|---|---|
| **رسائل SMS لرمز الدخول** | محاكٍ (`console`): الرمز يُسجَّل في السجل ويُعرض في واجهة التطوير فقط | حساب لدى مزود رسائل يغطي ليبيا (ليبيانا/المدار عبر مجمّع رسائل)، معرّف مرسل «AAWEN» معتمد | `SMS_PROVIDER=http`, `SMS_HTTP_URL`, `SMS_HTTP_TOKEN`, `SMS_SENDER_ID` — الموصل يرسل `POST {to, from, text}` بـ Bearer؛ عدّل `apps/notifications/channels.py` إن اختلف عقد المزود |
| **الإشعارات الفورية** | محاكٍ (`simulated`) يسجل كل إرسال في جدول `Delivery` بحالة `simulated` | مشروع Firebase (FCM) + حساب Apple Developer لـ APNs | `PUSH_PROVIDER=fcm`, `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_FILE` + `pip install google-auth` + إضافة `firebase_messaging` للتطبيق |
| **تخزين الوسائط S3** | نظام ملفات محلي | حاوية S3/R2/MinIO خاصة مع Versioning | `USE_S3=true`, `S3_*` |
| **بوابة الدفع** | محاكٍ موقّع (HMAC)، معلّم «محاكي» في كل الواجهات والسجل | اختيار مزود دفع ليبي (بطاقات محلية/محافظ)، عقد، حساب مستفيد باسم الجهة المشغلة، مفاتيح، سر الإشعارات، **تفويض مكتوب** | `PAYMENTS_MODE=live`, `PAYMENT_PROVIDER=generic_http`, `PAYMENT_HTTP_BASE_URL`, `PAYMENT_HTTP_API_KEY`, `PAYMENT_WEBHOOK_SECRET`, `PAYMENT_BENEFICIARY_CONFIGURED=true`, `PAYMENT_LIVE_AUTHORISED=true` |
| **اقتراح الفئة بالذكاء الاصطناعي** | محلي (كلمات مفتاحية عربية/ليبية) — يعمل ومختبر | مفتاح Anthropic (اختياري) | `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `AI_MODEL` — عند أي فشل يعود للمحلي تلقائيًا |
| **تفريغ الصوت** | غير مفعّل (`none`)؛ الإدخال اليدوي متاح دائمًا | خدمة تفريغ تدعم العربية الليبية | `TRANSCRIPTION_PROVIDER=http`, `TRANSCRIPTION_HTTP_URL` (يستقبل الصوت ويعيد `{"text": ...}`) |
| **بلاطات الخرائط** | OpenStreetMap العام (للتطوير فقط) | مزود بلاطات تجاري أو خادم خاص (سياسة OSM تمنع الاستخدام الكثيف) | `VITE_TILE_URL`, `VITE_TILE_ATTRIBUTION`, `--dart-define=AAWEN_TILES=` |
| **حدود المناطق الرسمية** | مستطيلات تقريبية للعرض | ملفات GeoJSON من البلديات/مصلحة التخطيط العمراني | أمر `import_areas` |
| **أرقام الطوارئ** | فارغة عمدًا | أرقام رسمية متحقق منها | شاشة الإعدادات |
| **متاجر التطبيقات** | — | Google Play Console ($25 مرة واحدة)، Apple Developer Program ($99 سنويًا) باسم الجهة المالكة | انظر `HANDOVER.md` |

## عقد موصل الدفع العام (`generic_http`)
- `POST {BASE}/checkouts` بجسم `{amount, currency, reference, return_url}` → `{id, url}`؛ يُوجَّه المساهم إلى `url`.
- الإشعارات إلى `POST /api/v1/finance/webhooks/generic_http` مع ترويسة `X-Gateway-Signature = HMAC-SHA256(body, PAYMENT_WEBHOOK_SECRET)` وجسم:
  `{event_id, type: payment.succeeded|payment.failed|refund.succeeded, checkout_id, amount, fee, refund_id?, failure_reason?}`.
- `POST {BASE}/refunds` بجسم `{checkout_id, amount}` → `{id}`.
- ضمانات النظام بغض النظر عن المزود: لا تُسجَّل الدفعة مرتين (حدث فريد + قيد تحصيل فريد لكل دفعة)، المبلغ المختلف يحوّل الدفعة إلى «تحتاج مراجعة» ولا يُسجَّل، والاسترداد لا يُقيَّد إلا بعد تأكيد المزود.

> إذا كان عقد المزود المختار مختلفًا، يُكتب صنف جديد في `apps/finance/providers.py` يطبق `create_checkout / verify_and_parse / refund`، دون تغيير بقية النظام.
