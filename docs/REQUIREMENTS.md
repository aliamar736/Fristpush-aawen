# سجل المتطلبات والتتبع — عاون

**مفتاح الحالة**
- ✅ **مختبر**: منفذ ومغطى باختبار آلي ناجح (pytest / vitest / Playwright).
- 🟢 **منفذ**: منفذ ويعمل يدويًا، دون اختبار آلي مخصص.
- 🟡 **جزئي**: منفذ جزئيًا — التفاصيل في عمود الملاحظات.
- 🔌 **ينتظر بيانات الربط**: الموصل مكتوب، ويعمل حاليًا بمحاكٍ صريح؛ لم يُجرَّب مع المزود الحقيقي.
- ⛔ **غير منفذ / غير مُتحقق**.

المسارات نسبية إلى جذر المستودع. `be/` = `backend/apps/`، `web/` = `web/src/`، `t/` = `backend/tests/`، `e2e/` = `web/e2e/`.

## 1. المنتجات والبنية
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| P1 | تطبيق هاتف أندرويد/آيفون | `mobile/lib/**` (Flutter) | `mobile/test/drafts_test.dart` (لم يُشغَّل) | ⛔ غير مُتحقق | الكود مكتوب كاملًا لكنه **لم يُبنَ** — Flutter غير متاح في بيئة التنفيذ. انظر `mobile/README.md` |
| P2 | بوابة ويب متجاوبة للمواطن | `web/pages/citizen/*` | `e2e/*.spec.ts` | ✅ | تُثبَّت كتطبيق ويب (PWA) — ليست تطبيقًا أصليًا |
| P3 | لوحة إدارة فريق عاون | `web/pages/admin/*` | `e2e/staff.spec.ts`, `e2e/a11y-rtl.spec.ts` | ✅ | |
| P4 | بوابة الجهات والشركاء | `web/pages/agency/Agency.tsx` | `e2e/staff.spec.ts` | ✅ | |
| P5 | واجهة ميدانية | `web/pages/agency/Agency.tsx` (FieldTasks) + `ReportWorkbench` | `e2e/finance-field.spec.ts` | ✅ | المسودات دون اتصال مفعلة للمواطن؛ إثبات الميدان يحتاج اتصالًا (🟡) |
| P6 | خادم/API/قاعدة بيانات مكانية/وسائط/إشعارات | `backend/` Django 5.2 + DRF + PostGIS 3.4 | كل `t/` | ✅ | |
| P7 | طابور مهام | `config/celery.py`, `be/*/tasks.py` | المهام تُختبر متزامنة (eager) | ✅ | Beat للجدولة: انتهاء التنبيهات، التصعيد، المراجعات اللاحقة |
| P8 | تخزين متوافق مع S3 | `config/settings.py` (`USE_S3`) | — | 🔌 | محليًا نظام ملفات؛ MinIO في compose (لم يُشغَّل هنا) |
| P9 | Docker | `infra/docker-compose.yml`, `*/Dockerfile` | `docker compose config` صالح | 🟡 | لم تُبنَ الصور: سجل Docker Hub محجوب في البيئة |
| P10 | وثائق API | `docs/openapi.yaml` (207 عملية)، `/api/v1/docs` | توليد بلا أخطاء | ✅ | |

## 2. الهوية وتجربة الاستخدام
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| B1 | الشعار العربي والرمز المعتمد، دون شعار جديد | `brand/svg/*` (تتبُّع متجهي من اللوحة) | مقارنة بصرية | 🟡 | مطابق بصريًا؛ مطلوب الأصل المتجهي الرسمي قبل الطباعة/المتاجر (`brand/README.md`) |
| B2 | الألوان الأربعة والعبارة | `web/styles.css`, `mobile/lib/theme.dart` | — | ✅ | نسخة أغمق من التركواز للنصوص لتحقيق تباين AA |
| B3 | خط عربي مرخّص | IBM Plex Sans Arabic (OFL) | — | ✅ | |
| B4 | RTL صحيح + إمكانية الإنجليزية | `web/lib/i18n.tsx`, `mobile/lib/l10n.dart` | `e2e/a11y-rtl.spec.ts` | ✅ | رسائل الخادم بالعربية فقط حاليًا |
| B5 | حالات التحميل/الخطأ/الفراغ/الانقطاع/رفض الصلاحية | `web/components/ui.tsx` | `e2e/a11y-rtl.spec.ts` (error, empty, offline) | ✅ | |
| B6 | قارئات الشاشة، تكبير الخط | ARIA، روابط تخطٍّ، تركيز مرئي | axe (WCAG 2 A/AA) على 13 صفحة + تكبير 200% | ✅ | فحص آلي فقط؛ يُنصح باختبار يدوي مع TalkBack/VoiceOver |
| B7 | أجهزة محدودة | تقسيم الكود، ضغط الصور، كاش الواجهة | حجم الحزمة الأولى ~70KB gzip | 🟢 | |
| B8 | عدم خلط بيانات العرض بالحقيقية | حقل `is_demo` + شارة «تجريبي» + `purge_demo` + رفض في الإنتاج | `t/test_accounts_ops.py` | ✅ | |

## 3. التبويبات
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| T1 | خمسة تبويبات + زر «بلّغ» | `web/components/Shell.tsx`, `mobile/lib/screens/shell.dart` | `e2e/a11y-rtl.spec.ts` | ✅ |
| T2 | حومتي: منطقة، ملخص، تنبيهات جهات، دليل موثق، اقتراحات، منجزات | `web/pages/citizen/Home.tsx`, `be/geo/views.py` (summary) | لقطات + a11y | 🟢 |
| T3 | الخريطة: طبقات مستقلة، فلاتر فئة/حالة/مصدر/وقت، تجميع | `MapPage.tsx`, `MapView.tsx` (markercluster) | a11y | 🟢 | فلتر «المصدر» متاح لتنبيهات الطريق؛ البلاغات مصدرها المواطن دائمًا |
| T4 | عاون: مبادرات، خُذ مهمة، مهاراتي، مخزن الخير، نقاط العناية | `Aawen.tsx` | `t/test_inventory_community.py` | ✅ |
| T5 | ساهم: احتياجات، عيني/خدمي/مالي، تعهدات، شركات، مصروفات ونتائج | `Contribute.tsx`, `Initiative.tsx` | `t/test_finance.py`, `e2e/finance-field.spec.ts` | ✅ |
| T6 | أثري: بلاغاتي، مهامي، مساهماتي، إشعارات، أدلة، اعتراضات، سجل مشاركة | `Impact.tsx`, `Misc.tsx` | e2e | ✅ |
| T7 | تصفح دون حساب، تحقق عند الإرسال | `IsAuthenticatedOrReadOnly`، OTP | `t/test_offline_and_privacy.py` | ✅ |

## 4. البلاغات ودورة المعالجة
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| R1 | فئات البداية الخمس + إضافة من الإدارة | `seed_reference`, `CategoryViewSet` | `test_category_admin_and_new_category_routes` | ✅ |
| R2 | موقع قابل للتعديل + معلم قريب | `Report.point/location_edited/landmark`، `/landmarks/near` | e2e report-flow | ✅ |
| R3 | صورة/صوت اختياري، وقت رصد منفصل | `MediaAsset`, `observed_at` | `test_observed_time_separate_and_not_in_future` | ✅ |
| R4 | رقم متابعة، جهة اختصاص، سجل حالات وأدلة | `tracking_number`, `ReportEvent`, `ReportMedia` | lifecycle | ✅ |
| R5 | بلاغات مشابهة قبل الإرسال + «أؤكد» | `similar_reports`, `confirm_existing` | `test_similar_reports_and_confirm…` + e2e | ✅ |
| R6 | الحالات الأربع عشرة | `be/reports/workflow.py` | `test_report_lifecycle.py` | ✅ |
| R7 | فصل الإحالة عن الاستلام | `Referral.acknowledged_at` | lifecycle + e2e staff | ✅ |
| R8 | لا إغلاق بمرور الوقت | لا مسار نظامي للإغلاق؛ التصعيد ينبه فقط | `test_reports_never_close_because_time_passed` | ✅ |
| R9 | توجيه بالمنطقة/الفئة/دليل الاختصاص + مراجعة الحدود | `be/reports/routing.py` | `test_routing_permissions.py` | ✅ |
| R10 | أولوية بالخطر والضرر والموقع والعمر والتكرار، لا الأصوات وحدها | `be/reports/priority.py` | `test_priority_not_driven_by_votes_alone` | ✅ |
| R11 | دمج البلاغات المكررة من طرف المراجع | — | — | ⛔ | يوجد منع التكرار للمواطن (التأكيد بدل الإرسال) فقط |

## 5. الطريق توّا
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| W1 | تنبيهات مؤقتة: حوادث/ازدحام/إغلاقات/عوائق | `be/roadnow/*`, `Road.tsx` | `t/test_roadnow.py` | ✅ |
| W2 | وقت الرصد وآخر تحديث، المصدر، التحقق، الصلاحية | `RoadAlert` fields | ✅ | ✅ |
| W3 | «ما زال موجود» / «الطريق فتح» | `services.vote` | `test_alert_expires_and_still_there_renews`, `test_road_open_votes_clear_alert` | ✅ |
| W4 | قواعد قابلة للضبط | `SystemSetting road_rules` + شاشة الإعدادات | `test_rules_are_configurable` | ✅ |
| W5 | معالجة الإرسال المتأخر | حالة `historical` | `test_delayed_submission_not_published_as_live` | ✅ |
| W6 | «ازدحام مبلّغ عنه» دون سرعات/مدد مختلقة | تسمية + عدم وجود حقول | `test_no_fabricated_traffic_metrics…` | ✅ |
| W7 | فصل بلاغ الخريطة عن النجدة | إشعار ثابت + أرقام رسمية من الإدارة فقط (فارغة افتراضيًا) | نفس الاختبار | ✅ |

## 6. المشاركة والتميز
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| E1 | خُذ مهمة: مدة/موقع/مهارة/مسؤول/عدد، حجز، تأكيد حضور، إثبات إتمام | `Task`, `TaskBooking` | `test_task_booking_capacity_attendance_completion` | ✅ |
| E2 | شن ناقص؟ + ربط عروض المساعدة | `Need.is_blocking`, `HelpOffer` | `test_blocking_needs_and_help_offer_lifecycle` | ✅ |
| E3 | مخزن الخير: متاح/محجوز/مستلم، إرجاع، حالة، مسؤول | `be/inventory/*` | `test_reserve_cancel_pickup_return_cycle`, `test_donation…` | ✅ |
| E4 | مهاراتي + ترشيح مهام | `VolunteerProfile`, `recommend_tasks` | `test_skills_profile_recommendations` | ✅ |
| E5 | ملف المكان | `PlaceProfileView` | لقطات | 🟢 |
| E6 | المشكلة رجعت (ربط بالإصلاح السابق + دليل جديد + مراجعة لاحقة قابلة للضبط) | `Recurrence`, `FollowUpReview` | `test_problem_returned_links_previous_fix…` | ✅ |
| E7 | شاهد الإنجاز: إثبات منفذ + تأكيد مستقل + مسار التعارض | `CompletionProof`, `CompletionCheck` | lifecycle + e2e field | ✅ |
| E8 | حزمة حل دون فقد حالة كل بلاغ | `ReportBundle` | `test_bundle_keeps_individual_report_status` | ✅ |
| E9 | اقتراحات الحومة: جدوى/إذن/تكلفة/صيانة ثم تصويت ضمن ميزانية | `Proposal`, `BudgetCycle` | `test_proposal_review_and_budget_constrained_voting` | ✅ |
| E10 | طريق للكل دون ضمان مسار | طبقة `pedestrian` | — | 🟢 |
| E11 | نقاط العناية الموثقة مع تاريخ التحقق | `CarePoint` | `test_care_points_only_verified_are_public` | ✅ |
| E12 | فائض ينفع، والغذاء معطل حتى التجهيز | `SurplusOffer` + `features.surplus_food` | `test_food_surplus_disabled_until_enabled` | ✅ |
| E13 | لوحة المناطق الأقل مشاركة + تكليف سفراء | `coverage`, `SurveyAssignment` | `test_coverage_dashboard_and_survey_assignment` | ✅ |

## 7. المساهمات والمحاسبة
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| F1 | ربط بمبادرات معتمدة واحتياجات محددة | `create_pledge` | `test_pledge_is_not_a_payment…` | ✅ |
| F2 | فصل التعهد عن الدفعة؛ العرض/الحجز/الاستلام | `Pledge`/`Payment`، `HelpOffer` | finance + community | ✅ |
| F3 | صورة التحويل ليست دفعة دون مطابقة | `TransferProof`, `match_transfer` | `test_transfer_screenshot_is_not_payment…` | ✅ |
| F4 | سجل قابل للتدقيق: تحصيل/رسوم/صرف/استرداد/رصيد | `LedgerEntry` + trigger يمنع التعديل | `test_ledger_is_immutable_at_database_level` | ✅ |
| F5 | فصل صلاحيات الصرف | `decide_disbursement`/`pay_disbursement` | `test_disbursement_separation_of_duties…`, `test_requester_cannot_approve…` | ✅ |
| F6 | الإشعارات المكررة من المزود لا تُسجَّل مرتين | `ProviderEvent` + قيود فريدة | `test_payment_success_with_duplicate_webhooks…` + e2e | ✅ |
| F7 | فشل الدفع والاسترداد | `handle_webhook`, `Refund` | `test_payment_failure…`, `test_refund_flow…` | ✅ |
| F8 | إيصالات ومستندات | رقم إيصال لكل دفعة؛ إيصال صرف مرفق إلزامي | finance | 🟡 | لا يُولَّد PDF للإيصال بعد |
| F9 | سياسات الإلغاء/الفائض/عدم اكتمال التمويل | نصوص قابلة للتعديل + إلغاء التعهد | — | 🟡 | لا يوجد إجراء آلي لعدم اكتمال التمويل؛ يُدار يدويًا (صرف/استرداد) |
| F10 | المطابقة والتقارير | `reconciliation_report`, CSV | finance | ✅ |
| F11 | لا محفظة بين الأفراد | لا نقاط نهاية | `test_no_person_to_person_wallet_endpoints` | ✅ |
| F12 | المال الحقيقي معطل حتى الضبط والتفويض | `providers.get_provider`, `live_missing` | `test_live_payments_disabled_until_configured` | ✅ |
| F13 | مزود دفع حقيقي | `GenericHttpProvider` | — | 🔌 | يحتاج اختيار مزود ليبي وعقدًا ومفاتيح |

## 8. الأدوار والخصوصية والأمن
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| S1 | عشرة أدوار | `accounts.models.Role` | — | ✅ |
| S2 | فرض الصلاحيات على الخادم بحسب الدور والمنطقة/الجهة | `accounts/permissions.py`, `workflow.actor_kinds` | `test_routing_permissions.py` | ✅ |
| S3 | سجل التغييرات الحساسة | `AuditLog` + trigger | role/finance tests | ✅ |
| S4 | حجب هوية المبلغ وحجب البيانات الشخصية | `PublicReportSerializer`, `mask_sensitive` | `test_public_view_hides_reporter…` | ✅ |
| S5 | منع نشر صور المصابين + مراجعة وطمس | `ModerationViewSet`, `blur_regions` | `test_media_private_until_moderated_and_blur` | ✅ |
| S6 | لا تتبع موقع مستمر | موقع لحظي عند الطلب فقط | مراجعة كود | 🟢 |
| S7 | مصادقة آمنة | OTP مُجزّأ، محاولات محدودة، JWT 15 دقيقة مع تدوير | `test_otp_login_flow_and_lockout` | ✅ |
| S8 | حدود الطلبات والرفع | DRF throttles، حدود حجم/نوع، فحص الصور | `test_upload_strips_exif_and_rejects_bad_files` | ✅ |
| S9 | حماية الأسرار | متغيرات بيئة، `SECRET_KEY` إلزامي في الإنتاج، لا أسرار في المستودع | فحص `check --deploy` | ✅ |
| S10 | إدارة الجلسات | قائمة وإلغاء | `test_sessions_list_and_revoke` | ✅ |
| S11 | طلبات حذف الحساب | مهلة 7 أيام ثم إخفاء الهوية | `test_account_deletion_anonymises…` | ✅ |
| S12 | نسخ احتياطي مع اختبار الاستعادة | `backup_db`, `restore_db` | `test_backup_and_restore_roundtrip` | ✅ |
| S13 | إنشاء المدير الأول بأمان، لا كلمات مرور افتراضية | `create_first_admin` | `test_first_admin_bootstrap_is_safe` | ✅ |

## 9. الاتصال الضعيف والذكاء الاصطناعي
| # | المتطلب | التنفيذ | الاختبار | الحالة | ملاحظات |
|---|---|---|---|---|---|
| O1 | مسودات محلية | `web/lib/drafts.ts` (IndexedDB)، `mobile/lib/drafts.dart` | `drafts.test.ts` | ✅ (ويب) |
| O2 | ضغط الصور | `web/lib/image.ts`, `flutter_image_compress` + إعادة ترميز بالخادم | upload test | ✅ |
| O3 | إعادة الإرسال بمعرف يمنع التكرار | `client_id` + `Idempotency-Key` + قفل استشاري | `test_concurrent_duplicate_submissions…` + e2e offline | ✅ |
| O4 | بيان قِدم البيانات المخزنة | `getCached` + `StaleNote` | e2e offline | ✅ |
| A1 | اقتراح الفئة | `ai/services.py` (محلي + Anthropic اختياري) | `test_ai_cannot_change_status_or_close` | ✅ محلي / 🔌 خارجي |
| A2 | تفريغ الصوت | موصل http + محاكٍ | — | 🔌 |
| A3 | كشف التشابه | جغرافي + فئة | similar test | ✅ |
| A4 | تنبيه البيانات الحساسة | `detect_sensitive` | privacy test | ✅ |
| A5 | بديل يدوي، وليس شرطًا للقبول | | `test_report_accepted_without_ai` | ✅ |
| A6 | لا يعتمد صحة/لا يغلق/لا يصرف | لا وصول للـ workflow أو السجل المالي | `test_ai_cannot_change_status_or_close` | ✅ |
