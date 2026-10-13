# تطبيق «عاون» للهاتف (Flutter — أندرويد وآيفون)

> **الحالة بصراحة:** كود التطبيق مكتوب كاملًا هنا، لكنه **لم يُبنَ ولم يُشغَّل ولم يُختبر** في بيئة التنفيذ،
> لأن Flutter/Dart غير متاحين ومصادر تنزيلهما (storage.googleapis.com, pub.dev) محجوبة فيها.
> أول خطوة عند الاستلام: البناء على جهاز مطور وإصلاح أي أخطاء تجميع (متوقع أن تكون قليلة لكن غير مستبعدة).

## ما يغطيه
- خمسة تبويبات: حومتي، الخريطة، عاون، ساهم، أثري + زر «بلّغ» المركزي.
- معالج البلاغ (المكان بالخريطة/موقع لحظي، الفئة، الوصف مع اقتراح ذكي اختياري وتحذير البيانات الحساسة،
  صور مضغوطة، تسجيل صوتي، وقت الرصد منفصل، بلاغات مشابهة مع «أؤكدها»، الإرسال).
- مسودات محلية في مجلد التطبيق، وإعادة إرسال تلقائية عند عودة الاتصال بمعرّف `client_id` يمنع التكرار،
  ولا تُعاد رفع الصور المرفوعة سابقًا.
- نسخة محفوظة من الصفحات مع بيان عمرها عند انقطاع الاتصال.
- تفاصيل البلاغ ومسار المعالجة، التأكيد، التحقق المستقل، الاعتراض، «المشكلة رجعت».
- الطريق توّا: إنشاء تنبيه، «ما زال موجود»، «الطريق فتح» — مع فصل واضح عن طلب النجدة.
- المهام، مخزن الخير، نقاط العناية، الاحتياجات والتعهدات، الإشعارات، الحساب وطلب الحذف.
- RTL كامل، الخط IBM Plex Sans Arabic (رخصة OFL في `assets/fonts/OFL-LICENSE.txt`)، دعم الإنجليزية.

غير مشمول في الهاتف (متاح في بوابة الويب): لوحة الإدارة وبوابة الجهات والمحاسبة.
الإشعارات الفورية (FCM/APNs) تحتاج حساب Firebase؛ الخادم جاهز (`PUSH_PROVIDER=fcm`) والتطبيق يحتاج إضافة `firebase_messaging` بعد الحصول على `google-services.json` و`GoogleService-Info.plist`.

## البناء
```bash
cd mobile
flutter create --org ly.aawen --project-name aawen --platforms=android,ios .   # يولّد مجلدي android/ و ios/
flutter pub get
dart run flutter_launcher_icons
flutter test
flutter run --dart-define=AAWEN_API=http://10.0.2.2:8000/api/v1          # محاكي أندرويد مع خادم محلي
flutter build appbundle --dart-define=AAWEN_API=https://api.example.ly/api/v1
flutter build ipa --dart-define=AAWEN_API=https://api.example.ly/api/v1
```
`AAWEN_TILES` يحدد خادم بلاطات الخريطة (الافتراضي OpenStreetMap — للإنتاج استخدم مزودًا تجاريًا أو خادمك؛ سياسة OSM لا تسمح بالاستخدام الكثيف).

## الأذونات (أضفها بعد `flutter create`)
**Android** `android/app/src/main/AndroidManifest.xml`:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
<uses-permission android:name="android.permission.CAMERA"/>
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
```
لا نطلب `ACCESS_BACKGROUND_LOCATION`: التطبيق لا يتتبع الموقع باستمرار.

**iOS** `ios/Runner/Info.plist`:
```xml
<key>NSLocationWhenInUseUsageDescription</key><string>لتحديد مكان المشكلة التي تبلّغ عنها فقط.</string>
<key>NSCameraUsageDescription</key><string>لتصوير المشكلة وإرفاقها بالبلاغ.</string>
<key>NSPhotoLibraryUsageDescription</key><string>لاختيار صورة للبلاغ.</string>
<key>NSMicrophoneUsageDescription</key><string>لتسجيل وصف صوتي للبلاغ.</string>
```
