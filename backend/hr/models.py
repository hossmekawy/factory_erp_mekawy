import datetime

from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم القسم")

    class Meta:
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"

    def __str__(self):
        return self.name


class Employee(models.Model):
    GENDER_CHOICES = (
        ("male", "ذكر"),
        ("female", "أنثى"),
    )

    employee_code = models.CharField(
        max_length=20, unique=True, verbose_name="كود الموظف (رقمه على جهاز البصمة)"
    )
    full_name = models.CharField(max_length=200, verbose_name="الاسم بالكامل")
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="القسم"
    )
    job_title = models.CharField(max_length=100, blank=True, verbose_name="المسمى الوظيفي")
    national_id = models.CharField(max_length=14, blank=True, verbose_name="الرقم القومي")
    phone_number = models.CharField(max_length=15, blank=True, verbose_name="رقم الهاتف")
    address = models.TextField(blank=True, verbose_name="العنوان")
    gender = models.CharField(
        max_length=10, choices=GENDER_CHOICES, default="male", verbose_name="الجنس"
    )
    birth_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الميلاد")
    hire_date = models.DateField(null=True, blank=True, verbose_name="تاريخ التعيين")
    salary = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="الراتب"
    )
    photo = models.ImageField(
        upload_to="employee_photos/", null=True, blank=True, verbose_name="صورة الموظف"
    )
    id_front_image = models.ImageField(
        upload_to="employee_ids/", null=True, blank=True, verbose_name="صورة وجه البطاقة"
    )
    id_back_image = models.ImageField(
        upload_to="employee_ids/", null=True, blank=True, verbose_name="صورة ظهر البطاقة"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    # Drives the team-leader picker on a cutting Lay; nothing else reads it.
    is_team_leader = models.BooleanField(default=False, verbose_name="رئيس فريق")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "موظف"
        verbose_name_plural = "الموظفون"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.employee_code} - {self.full_name}"


class WorkSchedule(models.Model):
    """Singleton: factory-wide work schedule (Sat-Thu, Friday off, 8:00-17:00)."""

    work_start = models.TimeField(default=datetime.time(8, 0), verbose_name="بداية الدوام")
    work_end = models.TimeField(default=datetime.time(17, 0), verbose_name="نهاية الدوام")
    # Python weekday numbers: Monday=0 ... Friday=4, Saturday=5, Sunday=6
    weekend_days = models.JSONField(default=list, verbose_name="أيام الإجازة الأسبوعية")

    class Meta:
        verbose_name = "جدول العمل"
        verbose_name_plural = "جدول العمل"

    def __str__(self):
        return f"{self.work_start} - {self.work_end}"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create(weekend_days=[4])  # Friday
        return obj


class SiteSettings(models.Model):
    """Singleton: branding shown in the browser tab, PWA install prompt, etc."""

    company_name = models.CharField(
        max_length=100, default="MR.Mekawy Factory ERP", verbose_name="اسم النظام"
    )
    favicon = models.ImageField(upload_to="site/", null=True, blank=True)
    icon_192 = models.ImageField(upload_to="site/", null=True, blank=True)
    icon_512 = models.ImageField(upload_to="site/", null=True, blank=True)
    apple_touch_icon = models.ImageField(upload_to="site/", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات النظام"
        verbose_name_plural = "إعدادات النظام"

    def __str__(self):
        return self.company_name

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj
