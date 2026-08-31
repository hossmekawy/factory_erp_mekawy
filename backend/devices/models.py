from django.db import models

from hr.models import Employee


class Device(models.Model):
    serial_number = models.CharField(max_length=50, unique=True, verbose_name="الرقم التسلسلي")
    name = models.CharField(max_length=100, blank=True, verbose_name="اسم الجهاز")
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name="آخر اتصال")
    push_version = models.CharField(max_length=20, blank=True)
    options_raw = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    # While set (until CLEAR DATA is confirmed), incoming pushes are dropped
    # so a wipe genuinely starts clean without the device re-populating data.
    wipe_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "جهاز بصمة"
        verbose_name_plural = "أجهزة البصمة"

    def __str__(self):
        return f"{self.name or 'ZKTeco'} ({self.serial_number})"


class AttendanceLog(models.Model):
    SOURCE_CHOICES = (
        ("device", "جهاز البصمة"),
        ("manual", "إدخال يدوي"),
    )

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="attendance_logs",
        verbose_name="الجهاز",
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_logs",
        verbose_name="الموظف",
    )
    employee_code = models.CharField(max_length=20, verbose_name="كود الموظف")
    timestamp = models.DateTimeField(verbose_name="وقت البصمة")
    punch_state = models.SmallIntegerField(default=0, verbose_name="نوع الحركة")
    verify_type = models.SmallIntegerField(default=1, verbose_name="طريقة التحقق")
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default="device", verbose_name="المصدر"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "سجل حضور"
        verbose_name_plural = "سجلات الحضور"
        constraints = [
            models.UniqueConstraint(
                fields=["device", "employee_code", "timestamp"], name="uniq_punch"
            )
        ]
        indexes = [models.Index(fields=["employee_code", "timestamp"])]
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.employee_code} @ {self.timestamp:%Y-%m-%d %H:%M}"


class FingerprintTemplate(models.Model):
    employee_code = models.CharField(max_length=20, verbose_name="كود الموظف")
    finger_id = models.SmallIntegerField(verbose_name="رقم الإصبع")  # 0-9
    template = models.TextField(verbose_name="القالب (base64)")
    valid = models.SmallIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "بصمة"
        verbose_name_plural = "البصمات"
        constraints = [
            models.UniqueConstraint(fields=["employee_code", "finger_id"], name="uniq_fp")
        ]

    def __str__(self):
        return f"FP {self.employee_code}/{self.finger_id}"


class DeviceCommand(models.Model):
    STATUS_CHOICES = (
        ("pending", "قيد الانتظار"),
        ("sent", "أُرسل للجهاز"),
        ("done", "تم التنفيذ"),
        ("failed", "فشل"),
    )

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="commands", verbose_name="الجهاز"
    )
    command = models.TextField(verbose_name="الأمر")
    description = models.CharField(max_length=200, blank=True, verbose_name="الوصف")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="pending", verbose_name="الحالة"
    )
    delivery_count = models.PositiveSmallIntegerField(default=0)
    return_code = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "أمر للجهاز"
        verbose_name_plural = "أوامر الأجهزة"
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.status}] {self.description or self.command[:40]}"
