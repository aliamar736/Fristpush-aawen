# دليل التشغيل والنشر والصيانة — عاون

## 1. التشغيل المحلي (دون Docker — الطريقة التي اختُبر بها المشروع)
المتطلبات: Python 3.12+، PostgreSQL 16 + PostGIS 3.4، Redis 7، Node 22، مكتبات GDAL/GEOS/PROJ.

```bash
# قاعدة البيانات
sudo -u postgres psql -c "CREATE ROLE aawen LOGIN PASSWORD 'devpass' CREATEDB;"
sudo -u postgres createdb -O aawen aawen
sudo -u postgres psql -d aawen -c "CREATE EXTENSION postgis; CREATE EXTENSION pg_trgm;"
# (الاختبارات تنشئ قاعدة test_aawen وتحتاج صلاحية إنشاء امتداد postgis: امنح الدور SUPERUSER في بيئة التطوير فقط)

# الخادم
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # عدّل القيم
python manage.py migrate
python manage.py seed_reference # فئات ومهارات ومدينة طرابلس (صالح للإنتاج)
python manage.py seed_demo      # بيانات عرض معلّمة «تجريبي» (مرفوض في الإنتاج)
python manage.py runserver
celery -A config worker -B -l info    # في نافذة أخرى

# الويب
cd web && npm ci && npm run dev       # http://localhost:5173 (يمرر /api إلى :8000)
```
حسابات العرض (بعد `seed_demo`): الدخول برقم الهاتف ورمز يظهر في واجهة الدخول (محاكي الرسائل في التطوير فقط):
`0910000001` مدير النظام · `0910000002` مراجع · `0910000003` منسق · `0910000004` موظف جهة النظافة · `0910000005` موظف الطرق ·
`0910000007` سفير · `0910000009` مسؤول مبادرة · `0910000010` محاسب · `0910000011` مراجع مالي · `0910000012` مواطن · `0910000014` فني ميداني.

## 2. التشغيل بـ Docker Compose
```bash
cp infra/.env.example infra/.env   # عيّن كلمات المرور والأسرار
docker compose -f infra/docker-compose.yml up --build
docker compose -f infra/docker-compose.yml exec api python manage.py create_first_admin --phone 09xxxxxxxx --name "..."
```
> لم تُبنَ هذه الصور في بيئة التنفيذ الأصلية (Docker Hub محجوب هناك)؛ صيغة الملف صالحة (`docker compose config`).

## 3. الاختبارات
```bash
scripts/test.sh        # الخادم (pytest + تغطية) + الويب (tsc + vitest) + E2E (يتطلب الخدمات تعمل)
scripts/e2e.sh         # يشغّل الخادم والويب ثم Playwright
SHOTS=1 npx playwright test e2e/screenshots.spec.ts   # يعيد توليد docs/screenshots
```
اختبار E2E يستخدم بيانات العرض ويحتاج رفع حدود الطلبات (السكربت يفعل ذلك عبر متغيرات `THROTTLE_*`).

## 4. النشر للإنتاج (عند التفويض فقط)
1. **بنية مقترحة**: خادم Linux (أو منصة حاويات) + PostgreSQL مُدار مع PostGIS + Redis مُدار + تخزين S3 (R2/S3/Wasabi) بإصدارات مفعلة + CDN أمام الويب.
2. **متغيرات إلزامية**: `AAWEN_ENV=production`، `SECRET_KEY` (≥50 حرفًا)، `DATABASE_URL`، `ALLOWED_HOSTS`، `CSRF_TRUSTED_ORIGINS`، `CORS_ALLOWED_ORIGINS`، `PUBLIC_WEB_URL`، وإعدادات S3.
   في الإنتاج: `DEBUG` معطل، ملفات تعريف الارتباط آمنة، HSTS، إعادة توجيه HTTPS، محاكي الدفع ممنوع، بيانات العرض ممنوعة، رمز الدخول لا يُعاد في الاستجابة.
3. `python manage.py migrate && python manage.py seed_reference && python manage.py check --deploy`
4. **المدير الأول**: `python manage.py create_first_admin --phone ... --name ...` (يطلب كلمة مرور تفاعليًا ويرفض التشغيل إن وُجد مدير). بقية الحسابات تُنشأ من «المستخدمون والأدوار».
5. **الحدود الجغرافية الحقيقية**: `python manage.py import_areas boundaries.geojson --city tripoli --source "بلدية طرابلس المركز 2026"`، ثم قواعد الاختصاص من «المناطق والجهات والتوجيه».
6. العمليات: `gunicorn` خلف Nginx (`web/nginx.conf`)، Celery worker + beat، مراقبة `/api/v1/health`.
7. **قبل الإطلاق العام**: مراجعة قانونية لسياسة الخصوصية وشروط الاستخدام، اتفاق مع مزود SMS، مزود بلاطات خرائط، أرقام طوارئ رسمية، وعدم تفعيل الدفع الحقيقي إلا بعد الإجراءات في `INTEGRATIONS.md`.

## 5. النسخ الاحتياطي والاستعادة
```bash
python manage.py backup_db --out /backups            # pg_dump -Fc + أرشيف الوسائط المحلية + manifest بالـ checksum وعدد الصفوف
python manage.py restore_db /backups/aawen-YYYYMMDD-HHMMSS.manifest.json --target-db aawen_restore_check
```
- الاستعادة ترفض الكتابة فوق القاعدة الحية دون `--drop-existing`، وتتحقق من الـ checksum ومن تطابق عدد الصفوف.
- اختبار الاستعادة مؤتمت: `test_backup_and_restore_roundtrip` (نجح).
- **الجدولة المقترحة**: نسخة يومية + احتفاظ 30 يومًا + نسخة أسبوعية خارج الموقع، واستعادة تجريبية شهرية إلى قاعدة مؤقتة. مع S3 فعّل Versioning والنسخ عبر المناطق.

## 6. الصيانة الدورية
| المهمة | التكرار |
|---|---|
| مراجعة قائمة «توجيه يحتاج مراجعة» و«إحالات متأخرة» | يوميًا |
| مراجعة الوسائط المعلقة | يوميًا |
| مطابقة التحويلات + تقرير المطابقة المالية | أسبوعيًا |
| تحقق نقاط العناية ودليل الخدمات (يظهر تاريخ آخر تحقق) | شهريًا |
| تحديث الحزم (`pip list --outdated`, `npm outdated`) وفحص الثغرات (`pip-audit`, `npm audit`) | شهريًا |
| استعادة تجريبية من نسخة احتياطية | شهريًا |
| حذف بيانات العرض قبل الإطلاق: `python manage.py purge_demo` | مرة واحدة |

## 7. استكشاف الأخطاء
- **`dev_code` لا يظهر**: يظهر فقط مع `SMS_PROVIDER=console` وخارج الإنتاج.
- **429 Too Many Requests**: حدود الطلبات (`THROTTLE_*`) — ارفعها مؤقتًا للاختبارات الآلية فقط.
- **البلاغ «يحتاج مراجعة توجيه»**: الموقع قرب حد منطقتين بجهتين مختلفتين، أو خارج التغطية، أو لا توجد قاعدة اختصاص.
- **الخريطة بلا بلاطات**: تحقق من `VITE_TILE_URL` ووصول الشبكة لمزود البلاطات.
