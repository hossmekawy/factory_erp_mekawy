# المرحلة ١ — تقرير الاستكشاف وقايمة الحذف

**التاريخ:** 31 أغسطس 2026
**النطاق:** موديول الإنتاج الحالي (Django app اسمه `cutting` + صفحات `/cutting` في الفرونت)
**الحالة:** لم يُحذف أي شيء. تقرير فقط.

---

## 0. تنبيه لازم يتحل قبل المرحلة ٢

| # | المشكلة | لماذا تهم |
|---|---|---|
| **A** | **`/root/factory_erp` مش git repository أصلاً.** الباك إند كله لم يدخل version control ولا مرة. | طلبك "اشتغل على branch جديد" **غير قابل للتنفيذ حالياً**. لازم `git init` في الروت أولاً + commit للحالة الحالية، وبعدها branch. |
| **B** | `frontend/.git` موجود لكن فيه **commit واحد فقط** (`66d7a13 Initial commit from Create Next App`). كل شغل الفرونت (employees، attendance، devices، cutting، users، settings، components، lib) **غير محفوظ** — untracked أو modified. | لو حصل أي خطأ في الحذف، مفيش نقطة رجوع للفرونت كله، مش بس موديول القص. |
| **C** | الخدمتين **شغالتين على الإنتاج**: `factory-erp-backend.service` و `factory-erp-frontend.service` على `factory.mekawyerp.shop`. | الحذف هيسقط صفحات شغالة. محتاج نافذة تنفيذ + restart مرتب. |

**اقتراحي للمرحلة ٢:** `git init` في `/root/factory_erp` بـ `.gitignore` مناسب (venv، node_modules، .next، media، *.log، .env) → commit "snapshot before cutting module removal" → `git checkout -b remove-old-cutting` → `pg_dump` → نبدأ الحذف.

---

## أ. خريطة النظام الحالي

**المشروع:** `/root/factory_erp` — باك إند Django + فرونت Next.js منفصلين.

### الباك إند (`/root/factory_erp/backend`)
- Django **5.2.16** · DRF **3.17.1** · SimpleJWT · django-filter 25.2 · PostgreSQL على **port 5433** (`factory_erp`)
- `LANGUAGE_CODE = "ar"` · `TIME_ZONE = "Africa/Cairo"` · `MEDIA_ROOT = backend/media`
- **مفيش Celery ولا django-q ولا أي task queue.** مفيش caching. مفيش logging config.
- **مفيش أي ملف tests في المشروع كله** (باك وفرونت).
- **مفيش audit/history tracking** (لا `django-simple-history` ولا غيره).
- PDF عن طريق `weasyprint`، إكسيل عن طريق `openpyxl` — نفس النمط في `hr` و `cutting`.

**الـ apps الأربعة:**

| App | الدور | الموديلات |
|---|---|---|
| `hr` | الموظفين والأقسام وجدول العمل وإعدادات الموقع والتقرير الأسبوعي والصلاحيات | `Department` · `Employee` · `WorkSchedule` · `SiteSettings` |
| `devices` | بروتوكول ZKTeco ADMS push، سجلات البصمة، القوالب، أوامر الأجهزة | `Device` · `AttendanceLog` · `FingerprintTemplate` · `DeviceCommand` |
| `cutting` | **الموديول المطلوب حذفه** | `CuttingOrder` · `Marker` · `MarkerSize` · `FabricRoll` |
| `config` | settings / urls / wsgi | — |

**الـ API:** `DefaultRouter` واحد في `config/urls.py` + دوال `@api_view` للحاجات المش-ViewSet. Pagination افتراضي 50. `DjangoFilterBackend` + `SearchFilter` + `OrderingFilter` مفعّلين globally.

**المستخدم:** `django.contrib.auth.User` الافتراضي — **مش custom**. الأدوار عن طريق **Groups**: `hr/permissions.py::role_of()` بيرجّع أول group من `ROLE_ORDER = ["admin", "hr", "production_manager", "cutting_supervisor", "cutting"]`.

**الربط بالبصمة:** الحقل اسمه **`Employee.employee_code`** (verbose_name: "كود الموظف (رقمه على جهاز البصمة)"). `AttendanceLog` بيربط بـ `employee_code` نص + FK اختياري على `Employee`.

### الفرونت (`/root/factory_erp/frontend`)
- Next.js **16.2.10** · React 19.2.4 · App Router · TypeScript · Tailwind v4 · lucide-react
- **مفيش react-query ولا SWR** — `fetch` يدوي عبر `lib/api.ts` (JWT + auto-refresh) و `useEffect`.
- RTL: `dir="rtl"` في `layout.tsx`، والخط **`Cairo`** من `next/font/google` (مش Tajawal).
- design system بسيط في `app/globals.css`: `.btn-primary` `.btn-secondary` `.btn-danger` `.card` `table.data` — لون العلامة أحمر (`red-600/700`).
- `components/Shell.tsx` = الـ layout والـ navigation والحماية بالدور.

---

## ب. ملفات موديول الإنتاج (الجرد الكامل)

### باك إند — `backend/cutting/` (15 ملف · 1194 سطر)

| الملف | أسطر | المحتوى |
|---|---|---|
| `models.py` | 181 | `CuttingOrder` · `Marker` · `MarkerSize` · `FabricRoll` |
| `serializers.py` | 224 | 5 serializers + التحققات |
| `views.py` | 168 | `CuttingOrderViewSet` + `size_suggestions` + `ocr_label` + 3 دوال تقارير |
| `ocr.py` | 143 | قراءة ليبل التوب بـ pytesseract |
| `reports.py` | 116 | بناء التقرير + تصدير إكسيل |
| `reports_pdf.py` | 79 | تصدير PDF (A4/A5) |
| `services.py` | 86 | `compute_summary()` — كل الحسابات |
| `permissions.py` | 30 | `IsCuttingStaff` · `CanTouchCutting` · `visible_cuttings` |
| `filters.py` | 23 | `CuttingOrderFilter` |
| `admin.py` | 20 | تسجيل في الـ Django admin مع inlines |
| `apps.py` | 6 | `CuttingConfig` |
| `__init__.py` | 0 | |
| `migrations/0001_initial.py` | 89 | إنشاء الجداول التلاتة الأولى |
| `migrations/0002_markersize.py` | 29 | إنشاء `MarkerSize` |
| `migrations/__init__.py` | 0 | |

**مفيش:** templates · tasks · signals · management commands · tests. الموديول باك-إند خالص + REST.

### فرونت — `frontend/app/cutting/` (4 صفحات · 1608 سطر)

| الملف | أسطر | الشاشة |
|---|---|---|
| `app/cutting/page.tsx` | 167 | قايمة القصات |
| `app/cutting/new/page.tsx` | 90 | قصة جديدة |
| `app/cutting/[id]/page.tsx` | **1104** | تفاصيل القصة (الفرشات + الأتواب + OCR + الملخص) |
| `app/cutting/reports/page.tsx` | 247 | تقارير القص + تصدير |

### ملفات الميديا
- `backend/media/cutting_worksheets/IMG_1989.jpeg` — ملف واحد (صورة ورقة القصة الوحيدة المسجلة).
- `roll_labels/` — **المجلد لم يُنشأ أصلاً** (مفيش أي صورة ليبل مرفوعة).

**إجمالي الكود المرشح للحذف: ~2800 سطر.**

---

## ج. كل حاجة بتعتمد عليه من بره

### FK داخلة على الموديول (من موديلات تانية إليه)
**لا يوجد ولا واحد.** جدول `cutting` مالوش أي مرجع من `hr` أو `devices`. الاتجاه واحد فقط:

```
cutting.CuttingOrder.created_by  ──PROTECT──►  auth.User
```
(FK خارج، مش داخل. حذف الموديول لا يمس `auth_user`.)

هذا أهم استنتاج في التقرير: **الموديول معزول بالكامل على مستوى الداتا.**

### الاعتمادات الفعلية (كلها imports وسطور نصية)

| # | المكان | السطر | النوع | التأثير |
|---|---|---|---|---|
| 1 | `config/settings.py:28` | `"cutting",` في `INSTALLED_APPS` | تسجيل app | يُحذف |
| 2 | `config/urls.py:8` | `from cutting import views as cutting_views` | import | يُحذف |
| 3 | `config/urls.py:20` | `router.register("cuttings", cutting_views.CuttingOrderViewSet)` | endpoint | يُحذف |
| 4 | `config/urls.py:41` | `path("api/cutting/ocr/", ...)` | endpoint | يُحذف |
| 5 | `config/urls.py:42` | `path("api/cutting/sizes/", ...)` | endpoint | يُحذف |
| 6 | `config/urls.py:43` | `path("api/cutting/reports/", ...)` | endpoint | يُحذف |
| 7 | `config/urls.py:44` | `path("api/cutting/reports/export/", ...)` | endpoint | يُحذف |
| 8 | `config/urls.py:45` | `path("api/cutting/reports/pdf/", ...)` | endpoint | يُحذف |
| 9 | `cutting/permissions.py:3` | `from hr.permissions import role_of` | import **خارج←داخل** | يختفي مع الملف. `hr` لا تتأثر. |
| 10 | `hr/permissions.py:5` | `ROLE_ORDER` فيه `"cutting_supervisor"` و `"cutting"` | نص | **اقتراحي: يُترك** (شوف تحت) |
| 11 | `frontend/components/Shell.tsx:43` | `const CUTTING_ROLES = [...]` | ثابت | يُعدّل |
| 12 | `frontend/components/Shell.tsx:66-67` | عنصرا التنقل "مرحلة القص" و"تقارير القص" | navigation | يُعدّل |
| 13 | `frontend/lib/roles.ts:9-10,17-19,26-28` | labels + ROLE_HOME + ROLE_PREFIXES | routing/حماية | يُعدّل |
| 14 | `frontend/app/users/page.tsx:114-115` | `<option value="cutting">` و `cutting_supervisor` | UI | يُعدّل |

**ملاحظة على البند 10 و 13:** الأدوار `cutting_supervisor` / `cutting` **مش خاصة بالكود القديم** — هي أدوار المصنع نفسها، والـ SRS بند ٣ محتاج نفس الأدوار للموديول الجديد. **اقتراحي: نسيبها زي ما هي** ونعيد ربطها بالموديول الجديد في المرحلة ٣، بدل ما نحذفها ونرجّعها.

### الصلاحيات في قاعدة البيانات
- `auth_group`: **3 مجموعات** — `admin` (3 مستخدمين) · `hr` (0) · `cutting` (0).
- `auth_group_permissions`: **0 صف** — مفيش صلاحيات Django مربوطة بأي group.
- **مفيش مستخدم واحد له دور قص.** كل المستخدمين الأربعة إما superuser أو في مجموعة `admin`.
- `auth_permission` فيه 16 صف تخص موديلات `cutting` (4 موديلات × 4 صلاحيات) — بتتشال أوتوماتيك مع الـ migration.

**الخلاصة: حذف الموديول لا يقطع الوصول عن أي مستخدم حالي.**

### الـ admin
`cutting/admin.py` بيسجّل `CuttingOrder` مع inlines لـ `Marker` و `FabricRoll`. بيختفي مع الملف. `admin.site.site_header` متعرّف في `hr/admin.py` — **لا يتأثر**.

---

## د. الـ Migrations

**migrations تخص الموديول:**
- `cutting/0001_initial.py` — `CuttingOrder` · `Marker` · `FabricRoll`
- `cutting/0002_markersize.py` — `MarkerSize`

**هل فيه migrations لموديلات تانية بتعتمد عليها؟ لأ.**
- `cutting/0001` بيعتمد على `swappable_dependency(AUTH_USER_MODEL)` فقط — اعتماد **خارج**، مش داخل.
- `hr/migrations` (0001, 0002) و `devices/migrations` (0001, 0002, 0003): **صفر إشارة** لـ `cutting`.
- `django_migrations` فيه 25 صف، منهم 2 لـ `cutting`.

**نتيجة عملية:** ممكن نشيل الـ app كامل ونعمل migration نضيفة تدرّوب الجداول، من غير ما نلمس أي migration تانية، ومن غير أي `RunPython` أو معالجة خاصة.

**الأسلوب المقترح (بما إنك طلبت متعدّلش القديم ومتمسحهوش):** نسيب `0001` و `0002` مكانهم، ونضيف `cutting/migrations/0003_drop_all.py` فيها `DeleteModel` للأربعة بالترتيب العكسي (`MarkerSize` → `FabricRoll` → `Marker` → `CuttingOrder`)، **ونشغّلها قبل** ما نحذف `cutting` من `INSTALLED_APPS` والملفات. الترتيب مهم: لو حذفنا الـ app الأول، Django مش هيقدر يشغّل الـ migration.

---

## هـ. البيانات الفعلية على قاعدة البيانات

```
cutting_cuttingorder   1 صف
cutting_marker         0
cutting_markersize     0
cutting_fabricroll     0
```

**الصف الوحيد بالتفصيل:**

| الحقل | القيمة |
|---|---|
| `id` | 2 |
| `code` | `1749` |
| `model_name` | رجالي نيولاند |
| `color` | كحلي / اسود |
| `production_order_no` | `1749` |
| `cutting_date` | 2026-07-09 |
| `created_by` | user id 1 (`admin`) |
| `worksheet_photo` | `cutting_worksheets/IMG_1989.jpeg` |
| `quick_total_meters` | فاضي |
| `has_shortage` | False — وكل حقول العجز فاضية |
| `notes` | فاضي |
| `created_at` | 2026-07-11 09:43 |

**الحكم:** ده **صف اختبار**، مش بيانات إنتاج. مفيش فرشات ولا أتواب ولا مقاسات مربوطة بيه (كلها أصفار). المعلومة الوحيدة اللي ليها قيمة هي **الصورة نفسها** `IMG_1989.jpeg` — دي صورة ورقة دفتر حقيقية، ومفيدة كمرجع بصري وأنت بتصمم شاشة "فرشة جديدة" في المرحلة ٣ (الـ SRS بند 7.2 بيقول الشاشة لازم تقلّد صفحة الدفتر بالظبط).

**اقتراحي:** ننسخ `IMG_1989.jpeg` لـ `/root/factory_erp/reference/` قبل الحذف ونسيبها هناك كمرجع تصميم، ونحذف صف الداتابيز عادي.

للمقارنة، الداتا الحقيقية في المشروع كلها في `hr` و `devices` ومش هتتلمس:
`devices_attendancelog` 1673 · `devices_devicecommand` 180 · `devices_fingerprinttemplate` 30 · `hr_employee` 22 · `hr_department` 3.

---

## و. اللي يستاهل يتنقذ

قريت الـ 2800 سطر. دي حكمي بصراحة:

### ✅ ١. `cutting/ocr.py` — أنقذه (143 سطر)
أحسن ملف في الموديول بفارق كبير، ومستقل بالكامل (بياخد ملف صورة ويرجّع dict، **مفيش أي import من `models` أو `views`**).
- fuzzy matching بـ `difflib` مع cutoff مضبوط على 0.72 وتعليق بيشرح ليه (عشان `order no` ماتتلخبطش مع `roll no`)
- إصلاح خلط OCR بين الحروف والأرقام (`O→0`, `l→1`, `S→5`) **جوه القيم الرقمية بس**
- `PLAUSIBLE` ranges: لو الطول قرا 5000 متر بيرفضه بتحذير عربي بدل ما يخمّن
- `_split_pairs` بتتعامل مع الليبلات اللي بتطبع حقلين على نفس السطر — دي حالة حقيقية من التيكتات
- بيشغّل psm 6 و psm 4 ويدمج النتيجتين

**السبب إنه مهم للجديد:** الـ SRS بند 4.3.1 نقطة ٤ بيقول صورة التيكت بتترفع من دلوقتي "والبيانات موجودة في الصورة ونقدر نستخرجها بعدين". والملف ده بيستخرج بالظبط `article` · `lot_no` · `roll_no` · `width_cm` · `net_weight_kg` — نفس حقول `LayLine` في بند 4.8. **ده شغل جاهز يخدم الموديول الجديد.**

⚠️ ملاحظة: `pytesseract` **مش موجود في `requirements.txt`** رغم إن الكود بيستورده. البايناري `/usr/bin/tesseract` والباكدج 0.3.13 متسطبين في الـ venv. يعني `pip install -r requirements.txt` على سيرفر جديد **هيكسر الموديول**. باگ قايم، لازم يتصلح في أي الحالتين.

### 🟡 ٢. فكرة `compute_summary()` — انقذ الفكرة، مش الكود
النمط صح: **دالة واحدة هي المصدر الوحيد لكل الأرقام المحسوبة**، والـ serializer والتقرير والـ API كلهم بينادوها. ده اللي الـ SRS محتاجه في بند 5.2 و 5.3.

**بس الكود نفسه فيه غلطتين حقيقيتين:**
- `expected_metraj` بياخد **أول فرشة بس** (`markers[0]`) ويتجاهل الباقي، رغم إن التعليق مكتوب فيه "Weighted across markers" — التعليق بيوصف حاجة الكود مش بيعملها.
- `real_metraj` = الأمتار ÷ **القطع النظرية**. الـ SRS بند 5.2 صريح إنه لازم يكون ÷ **القطع الفعلية من الترقيم** — وده جوهر الموديول الجديد كله. الحساب القديم غلط من أساسه.

**الحكم: خد التنظيم (`services.py` كطبقة منطق منفصلة)، اكتب الحسابات من الصفر.**

### 🟡 ٣. نمط `permissions.py` — انقذ النمط
`visible_cuttings(user, qs)` كدالة واحدة بتفلتر الـ queryset حسب الدور، ومنادَاة من الـ ViewSet ومن التقارير مع بعض — ده منع تسريب بيانات في التقارير بشكل نضيف. الفكرة تتكرر في `cutting` الجديد.

### 🟡 ٤. نمط التقارير (`reports.py` + `reports_pdf.py`) — انقذ الهيكل
`build_*_report()` بترجّع dict واحد، وبعدين render لـ JSON / إكسيل / PDF من نفس الـ dict. `COLUMNS` كقايمة واحدة بتتشارك بين الإكسيل والـ PDF فمستحيل يختلفوا. ده نفس نمط `hr/reports.py` أصلاً — يعني هو **أسلوب البيت**، والموديول الجديد يمشي عليه في المرحلة ٢ من الـ SRS.

### ❌ ٥. مش يستاهل — يتساب ورانا
- **الموديلات كلها.** `CuttingOrder` كيان مش موجود في الـ SRS خالص. `Marker`/`MarkerSize` بيمثلوا المقاسات كصفوف `label+ratio` — الـ SRS عايز نص متتابع `30 32 32 34 34 36` يتفك أوتوماتيك، ده تصميم مختلف. `FabricRoll` كجدول منفصل **مرفوض صراحة** في SRS بند 4.3 ("مفيش `FabricRoll` كجدول مخزون").
- **`app/cutting/[id]/page.tsx` (1104 سطر).** ملف واحد فيه كل شاشة التفاصيل والفرشات والأتواب والـ OCR. مافيهوش أي component قابل لإعادة الاستخدام، والـ SRS عايز تصميم موبايل-أولاً مختلف تماماً.
- **`filters.py`** — 6 فلاتر بسيطة. الـ SRS بند 7.1.2 عايز ~30 فلتر في 10 مجموعات. يتكتب من الأول.
- **`serializers.py`** — مربوط بموديلات هتختفي.

---

## قايمة الحذف

### باك إند

| # | العنصر | النوع | الخطورة | السبب |
|---|---|---|---|---|
| 1 | `backend/cutting/models.py` | حذف ملف | 🟢 **منخفضة** | مفيش FK داخل عليه من أي app |
| 2 | `backend/cutting/serializers.py` | حذف ملف | 🟢 منخفضة | مستخدم داخلياً فقط |
| 3 | `backend/cutting/views.py` | حذف ملف | 🟡 **متوسطة** | مربوط بـ `config/urls.py` — لازم يتشالوا مع بعض |
| 4 | `backend/cutting/services.py` | حذف ملف | 🟢 منخفضة | |
| 5 | `backend/cutting/filters.py` | حذف ملف | 🟢 منخفضة | |
| 6 | `backend/cutting/permissions.py` | حذف ملف | 🟢 منخفضة | بيستورد من `hr`، مش العكس |
| 7 | `backend/cutting/reports.py` | حذف ملف | 🟢 منخفضة | |
| 8 | `backend/cutting/reports_pdf.py` | حذف ملف | 🟢 منخفضة | |
| 9 | `backend/cutting/admin.py` | حذف ملف | 🟢 منخفضة | |
| 10 | `backend/cutting/ocr.py` | **نقل** لـ `reference/salvaged/ocr.py` | 🟢 منخفضة | مرشّح إنقاذ — بانتظار موافقتك |
| 11 | `backend/cutting/apps.py` + `__init__.py` | حذف ملف | 🟢 منخفضة | |
| 12 | `cutting/migrations/0003_drop_all.py` | **إنشاء** ثم تشغيل | 🔴 **عالية** | العملية الوحيدة اللي بتلمس قاعدة البيانات. لازم `pg_dump` قبلها |
| 13 | جدول `cutting_cuttingorder` (1 صف) | DROP | 🟡 متوسطة | صف اختبار — الصورة تُنسخ قبلها |
| 14 | جداول `cutting_marker` · `cutting_markersize` · `cutting_fabricroll` | DROP | 🟢 منخفضة | **فاضية تماماً** |
| 15 | 16 صف في `auth_permission` | يتشالوا مع الـ migration | 🟢 منخفضة | مفيش group مربوط بيهم |
| 16 | `backend/cutting/` (المجلد) | حذف مجلد | 🟢 منخفضة | آخر خطوة |
| 17 | `config/settings.py:28` — `"cutting",` | حذف سطر | 🟡 متوسطة | **بعد** تشغيل migration 0003 |
| 18 | `config/urls.py:8,20,41,42,43,44,45` | حذف 7 أسطر | 🟡 متوسطة | الـ import والسطور الستة مع بعض |
| 19 | `hr/permissions.py:5` — الأدوار | **لا يُحذف** | — | مطلوبة للموديول الجديد (SRS بند ٣) |
| 20 | `backend/media/cutting_worksheets/` | نقل ثم حذف | 🟢 منخفضة | ملف واحد → `reference/` |

### فرونت إند

| # | العنصر | النوع | الخطورة | السبب |
|---|---|---|---|---|
| 21 | `frontend/app/cutting/page.tsx` | حذف ملف | 🟢 منخفضة | |
| 22 | `frontend/app/cutting/new/page.tsx` | حذف ملف | 🟢 منخفضة | |
| 23 | `frontend/app/cutting/[id]/page.tsx` | حذف ملف | 🟢 منخفضة | |
| 24 | `frontend/app/cutting/reports/page.tsx` | حذف ملف | 🟢 منخفضة | |
| 25 | `frontend/app/cutting/` (المجلد) | حذف مجلد | 🟢 منخفضة | |
| 26 | `Shell.tsx:66-67` — عنصرا التنقل | حذف سطرين | 🟡 متوسطة | مجموعة "الإنتاج" هتبقى **فاضية** — لازم تتشال هي كمان أو يتساب placeholder |
| 27 | `Shell.tsx:43` — `CUTTING_ROLES` | حذف مؤقت | 🟢 منخفضة | هترجع في المرحلة ٣ |
| 28 | `lib/roles.ts:17-19` — `ROLE_HOME` | **تعديل** | 🔴 **عالية** | لو `production_manager` فضل موجّه لـ `/cutting` المحذوفة، **هيدخل في redirect loop عند تسجيل الدخول**. لازم يتحوّل لـ `/` مؤقتاً |
| 29 | `lib/roles.ts:26-28` — `ROLE_PREFIXES` | تعديل | 🟡 متوسطة | نفس السبب — دور بمصفوفة فاضية = ممنوع من كل حاجة |
| 30 | `lib/roles.ts:9-10` — `ROLE_LABEL` | **لا يُحذف** | — | أسماء الأدوار مطلوبة في شاشة المستخدمين |
| 31 | `app/users/page.tsx:114-115` | **لا يُحذف** | — | نفس السبب |
| 32 | `frontend/.next/` | rebuild | 🟢 منخفضة | `npm run build` بعد الحذف |

### أعلى ٣ مخاطر

1. 🔴 **`lib/roles.ts` — `ROLE_HOME`** (بند 28). دي المخاطرة اللي بتكسر تسجيل الدخول فعلياً. حالياً `production_manager` و `cutting_supervisor` و `cutting` كلهم بيتوجهوا لـ `/cutting` بعد الـ login. لو الصفحة اتشالت والسطر فضل → لوب. **مخففة عملياً:** مفيش مستخدم حالي بأي دور من التلاتة (كلهم `admin`)، لكن لازم يتصلح قبل ما تعمل أول مستخدم قص.

2. 🔴 **migration الدروب** (بند 12). العملية الوحيدة غير القابلة للتراجع. مخففة بـ `pg_dump` + إن الجداول شبه فاضية.

3. 🟡 **ترتيب `INSTALLED_APPS`** (بند 17). لو اتشال `"cutting"` قبل تشغيل migration 0003، Django مش هيلاقي الـ app والجداول هتفضل يتيمة في الداتابيز — وهتحتاج SQL يدوي تنضفها. **الترتيب إجباري: migration الأول، الحذف بعدين.**

---

## خطة المرحلة ٢ (للموافقة)

1. `git init` في الروت + `.gitignore` + commit للحالة الحالية *(تنبيه A و B)*
2. `git checkout -b remove-old-cutting`
3. `pg_dump` كامل لـ `/root/factory_erp/backups/pre-cutting-removal-YYYYMMDD.sql`
4. نسخ `IMG_1989.jpeg` و `ocr.py` لـ `reference/`
5. كتابة `cutting/migrations/0003_drop_all.py` و `migrate`
6. حذف مجلد `backend/cutting/`
7. تنظيف `settings.py` و `config/urls.py`
8. حذف `frontend/app/cutting/` وتعديل `Shell.tsx` و `lib/roles.ts`
9. تحقق: `makemigrations --check` · `manage.py check` · `npm run build` · restart الخدمتين · اختبار `/login` والصفحات الباقية
10. تقرير بالتفصيل

---

## أسئلة محتاج إجابتها قبل المرحلة ٢

| # | السؤال | اقتراحي |
|---|---|---|
| 1 | أعمل `git init` في `/root/factory_erp`؟ من غيره مفيش branch ولا rollback. | **نعم** — وكمان commit لشغل الفرونت غير المحفوظ قبل أي حاجة |
| 2 | أنقذ `ocr.py`؟ | **نعم** — انقله لـ `reference/salvaged/`، وقرر في المرحلة ٣ تستخدمه أو لأ |
| 3 | الصف الوحيد (كود 1749) — أحذفه؟ | **نعم**، مع الاحتفاظ بالصورة كمرجع تصميم |
| 4 | أدوار `cutting` / `cutting_supervisor` — أسيبها؟ | **نعم** — الـ SRS محتاجها، حذفها ورجوعها شغل زيادة |
| 5 | مجموعة "الإنتاج" في القائمة بعد الحذف — أشيلها ولا أسيبها فاضية؟ | **شيلها مؤقتاً** وترجع في المرحلة ٣ |
| 6 | أعمل restart للخدمات بعد الحذف على الإنتاج مباشرة؟ | **نعم** — الموقع هيبقى من غير موديول قص لحد المرحلة ٣، وده متوقع |
