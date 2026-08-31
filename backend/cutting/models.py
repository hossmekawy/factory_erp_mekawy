from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CuttingOrder(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="كود القصة")
    model_name = models.CharField(max_length=200, verbose_name="اسم الموديل")
    color = models.CharField(max_length=100, blank=True, verbose_name="اللون")
    production_order_no = models.CharField(
        max_length=100, blank=True, verbose_name="رقم أمر الإنتاج"
    )
    cutting_date = models.DateField(default=timezone.localdate, verbose_name="تاريخ القص")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="cuttings", verbose_name="موظف القص"
    )
    worksheet_photo = models.ImageField(
        upload_to="cutting_worksheets/", null=True, blank=True,
        verbose_name="صورة ورقة القصة",
    )
    # Quick-entry shortcut: total fabric meters entered directly instead of
    # itemizing every roll. When set it overrides the sum of roll lengths.
    quick_total_meters = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="إجمالي الأمتار (إدخال سريع)",
    )
    has_shortage = models.BooleanField(default=False, verbose_name="يوجد عجز")
    shortage_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="كمية العجز"
    )
    shortage_reason = models.CharField(max_length=200, blank=True, verbose_name="سبب العجز")
    shortage_notes = models.TextField(blank=True, verbose_name="ملاحظات العجز")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "قصة"
        verbose_name_plural = "القصات"
        ordering = ["-cutting_date", "-id"]

    def __str__(self):
        return f"{self.code} — {self.model_name}"


class Marker(models.Model):
    cutting = models.ForeignKey(
        CuttingOrder, on_delete=models.CASCADE, related_name="markers", verbose_name="القصة"
    )
    fabric_width = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="عرض الفرشة (سم)"
    )
    marker_length = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name="طول الفرشة (متر)"
    )
    min_top_length = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="أقل توب (متر)"
    )
    pieces_per_lay = models.PositiveIntegerField(verbose_name="عدد القطع في الراقة")
    layers_count = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="عدد الطبقات"
    )
    lays_count = models.PositiveIntegerField(verbose_name="عدد الراقات")

    class Meta:
        verbose_name = "فرشة"
        verbose_name_plural = "الفرشات"
        ordering = ["id"]

    def __str__(self):
        return f"فرشة {self.id} — {self.cutting.code}"

    @property
    def expected_metraj(self):
        if not self.pieces_per_lay:
            return None
        return self.marker_length / self.pieces_per_lay

    @property
    def total_pieces(self):
        return self.pieces_per_lay * self.lays_count


class MarkerSize(models.Model):
    """Size ratio inside one marker: e.g. مقاس 32 × قطعتين في الراقة.
    When a marker has sizes, its pieces_per_lay = Σ ratios (kept in sync by
    the serializer). Labels are free text so any sizing system works."""

    marker = models.ForeignKey(
        Marker, on_delete=models.CASCADE, related_name="sizes", verbose_name="الفرشة"
    )
    label = models.CharField(max_length=30, verbose_name="المقاس")
    ratio = models.PositiveIntegerField(default=1, verbose_name="عدد القطع في الراقة")

    class Meta:
        verbose_name = "مقاس"
        verbose_name_plural = "المقاسات"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["marker", "label"], name="uniq_size_per_marker")
        ]

    def __str__(self):
        return f"{self.label} × {self.ratio}"

    @property
    def total_pieces(self):
        return self.ratio * self.marker.lays_count


class FabricRoll(models.Model):
    STATUS_CHOICES = [
        ("open", "قيد الاستخدام"),
        ("finished", "خلص"),
        ("remnant", "به باقي"),
    ]

    cutting = models.ForeignKey(
        CuttingOrder, on_delete=models.CASCADE, related_name="rolls", verbose_name="القصة"
    )
    marker = models.ForeignKey(
        Marker, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rolls", verbose_name="الفرشة",
    )
    roll_number = models.CharField(max_length=100, blank=True, verbose_name="رقم التوب")
    lot_number = models.CharField(max_length=100, blank=True, verbose_name="رقم اللوط")
    article_name = models.CharField(max_length=200, blank=True, verbose_name="اسم الخامة")
    color = models.CharField(max_length=100, verbose_name="اللون")
    width = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="العرض (سم)"
    )
    length = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="الطول (متر)")
    weight = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, verbose_name="الوزن (كجم)"
    )
    grade = models.CharField(max_length=50, blank=True, verbose_name="الدرجة")
    lays_used = models.PositiveIntegerField(default=0, verbose_name="الراق المستخدم")
    actual_remaining = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name="الباقي الفعلي (متر)",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="open", verbose_name="الحالة"
    )
    label_photo = models.ImageField(
        upload_to="roll_labels/", null=True, blank=True, verbose_name="صورة الليبل"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "توب"
        verbose_name_plural = "الأتواب"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cutting", "roll_number"],
                condition=~Q(roll_number=""),
                name="uniq_rollno_per_cutting",
            )
        ]

    def __str__(self):
        return f"توب {self.roll_number or self.id} — {self.cutting.code}"

    def _marker(self):
        return self.marker or self.cutting.markers.first()

    @property
    def expected_remaining(self):
        m = self._marker()
        if m is None or not self.lays_used:
            return None
        return self.length - self.lays_used * m.marker_length

    @property
    def remaining_diff(self):
        exp = self.expected_remaining
        if exp is None or self.actual_remaining is None:
            return None
        return self.actual_remaining - exp
