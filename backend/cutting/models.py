"""Cutting / spreading module — the notebook page, as a database.

Field-level and line-level rules (V2, V3, V4, V6) are enforced in `clean()`
so they hold whatever writes the row. The whole-lay rules that only make sense
at closing time (V1, V5, V7, V8, V9) live in `validators.py` and run from
`services.close_lay` / `services.record_output`.

Nothing in here calculates. Every derived number on `Lay` is written by
`services.recalculate`; see the docstring there for why they are stored
columns and not properties.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction

from hr.models import Employee

from . import sizes as size_utils


def lay_image_path(instance, filename):
    """media/cutting/{year}/{month}/... — SRS section 10."""
    lay = instance if isinstance(instance, Lay) else instance.lay
    return f"cutting/{lay.start_date:%Y/%m}/{filename}"


class Bank(models.Model):
    """A spreading table on the factory floor."""

    code = models.CharField(max_length=20, unique=True, verbose_name="كود البنك")
    name = models.CharField(max_length=100, verbose_name="اسم البنك")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "بنك"
        verbose_name_plural = "البنوك"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class SizeSet(models.Model):
    """A reusable run of sizes, written the way the supervisor says it.

    `sizes_raw` is the source of truth; `total_pieces` is derived from it on
    save and is what fills `Lay.pieces_per_ply`.
    """

    name = models.CharField(max_length=100, verbose_name="اسم الطقم")
    sizes_raw = models.CharField(max_length=200, verbose_name="المقاسات")
    total_pieces = models.PositiveIntegerField(default=0, verbose_name="عدد القطع في الراق")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "طقم مقاسات"
        verbose_name_plural = "أطقم المقاسات"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sizes_raw})"

    def parsed(self):
        """[(size, pieces_in_ply), ...] in notebook order."""
        return size_utils.parse_sizes(self.sizes_raw)

    def clean(self):
        try:
            size_utils.parse_sizes(self.sizes_raw)
        except size_utils.SizeParseError as exc:
            raise ValidationError(
                {"sizes_raw": ValidationError(str(exc), code="sizes_unreadable")}
            )

    def save(self, *args, **kwargs):
        self.total_pieces = size_utils.total_pieces(self.sizes_raw)
        super().save(*args, **kwargs)


class Category(models.Model):
    """The section a model belongs to — رجالي · حريمي · مواليد · رجالي جامبو …

    A catalogue rather than a fixed choices list, because the sections are the
    factory's own and they add to them. Every model must carry one: it is the
    axis the reports are read along, and a model without a section is a model
    that falls out of every filter.
    """

    name = models.CharField(max_length=50, unique=True, verbose_name="القسم")
    notes = models.CharField(max_length=200, blank=True, verbose_name="ملاحظات")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class GarmentModel(models.Model):
    """Catalogue of garment models.

    Named `GarmentModel` and not `Model`: the latter shadows
    `django.db.models.Model`. The API path stays `/api/cutting/models/`.
    """

    # Generated, never typed. The number the supervisor writes in the notebook
    # is the code of the cutting run, not of the model — see Lay.code. Models
    # are found by name ("كارل رجالي"), so this is only a stable internal
    # handle, counting up from 1.
    code = models.CharField(
        max_length=30, unique=True, db_index=True, blank=True, verbose_name="كود الموديل"
    )
    name = models.CharField(max_length=100, verbose_name="اسم الموديل")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=False,
        related_name="models",
        verbose_name="القسم",
    )
    default_size_set = models.ForeignKey(
        SizeSet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="models",
        verbose_name="طقم المقاسات المعتاد",
    )
    image = models.ImageField(
        upload_to="cutting/models/", null=True, blank=True, verbose_name="صورة الموديل"
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "موديل"
        verbose_name_plural = "الموديلات"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def next_code(cls) -> str:
        """The next free number. Codes that are not numbers are ignored, so a
        hand-typed one from before this was generated cannot stall the count."""
        numbers = [
            int(c) for c in cls.objects.values_list("code", flat=True) if c and c.isdigit()
        ]
        return str(max(numbers, default=0) + 1)

    def save(self, *args, **kwargs):
        if not self.code:
            # Retry once: two people adding a model at the same moment would
            # otherwise collide on the unique index.
            for _ in range(5):
                self.code = self.next_code()
                try:
                    with transaction.atomic():
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.code = ""
            raise IntegrityError("تعذّر توليد كود للموديل")
        return super().save(*args, **kwargs)


class CuttingSettings(models.Model):
    """Singleton, same `get_solo()` pattern as hr.WorkSchedule."""

    fabric_tolerance_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.50"), verbose_name="تسامح القماش %"
    )
    pieces_tolerance_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("2.00"), verbose_name="تسامح القطع %"
    )
    remnant_waste_threshold_m = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("1.00"), verbose_name="حد الباقي الهالك (م)"
    )
    notify_emails = models.TextField(blank=True, verbose_name="إيميلات التنبيهات")

    # Preselected on the new-lay screen. Almost every lay runs on the same bank
    # with the same team leader, so making them a stored default saves two
    # taps per lay; the supervisor can still change either one.
    default_bank = models.ForeignKey(
        "Bank",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="البنك الافتراضي",
    )
    default_team_leader = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="رئيس الفريق الافتراضي",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات القص"
        verbose_name_plural = "إعدادات القص"

    def __str__(self):
        return "إعدادات القص"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class Lay(models.Model):
    """One spread on one bank: one model, one size set, one team leader."""

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_COUNTED = "counted"
    STATUS_APPROVED = "approved"
    STATUS_CHOICES = (
        (STATUS_OPEN, "مفتوحة"),
        (STATUS_CLOSED, "مقفولة"),
        (STATUS_COUNTED, "مترقّمة"),
        (STATUS_APPROVED, "معتمدة"),
    )

    MODE_DETAILED = "detailed"
    MODE_QUICK = "quick"
    ENTRY_MODE_CHOICES = ((MODE_DETAILED, "تفصيلي"), (MODE_QUICK, "سريع"))

    # The number written at the top of the notebook page. It belongs to the
    # cutting run, not to the garment model: the same model is cut many times
    # and gets a fresh code each time so two runs never get mixed up.
    code = models.CharField(
        max_length=30, unique=True, db_index=True, verbose_name="كود القصة"
    )

    # --- dates -----------------------------------------------------------
    start_date = models.DateField(verbose_name="تاريخ البداية")
    # Never null: an intersection filter on COALESCE(end_date, start_date)
    # cannot use the index. Defaults to start_date for a same-day lay.
    end_date = models.DateField(verbose_name="تاريخ النهاية")

    # --- relations -------------------------------------------------------
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="lays", verbose_name="البنك")
    garment_model = models.ForeignKey(
        GarmentModel, on_delete=models.PROTECT, related_name="lays", verbose_name="الموديل"
    )
    size_set = models.ForeignKey(
        SizeSet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lays",
        verbose_name="طقم المقاسات",
    )
    team_leader = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="led_lays", verbose_name="رئيس الفريق"
    )
    team_members = models.ManyToManyField(
        Employee, blank=True, related_name="member_lays", verbose_name="باقي الفريق"
    )
    entered_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="entered_lays", verbose_name="أدخلها"
    )

    # --- measurements ----------------------------------------------------
    lay_width_cm = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="عرض الفرشة (سم)",
    )
    narrowest_width_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="عرض أضيق توب (سم)"
    )
    lay_length_m = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="طول الفرشة (م)",
    )
    pieces_per_ply = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name="عدد القطع في الراق"
    )

    # --- state -----------------------------------------------------------
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN, verbose_name="الحالة"
    )
    entry_mode = models.CharField(
        max_length=10, choices=ENTRY_MODE_CHOICES, default=MODE_DETAILED, verbose_name="وضع الإدخال"
    )
    is_backfill = models.BooleanField(default=False, verbose_name="إدخال أثري")
    has_splice = models.BooleanField(default=False, verbose_name="فيها وصل")

    # --- documents -------------------------------------------------------
    sheet_image = models.ImageField(
        upload_to=lay_image_path, null=True, blank=True, verbose_name="صورة ورقة الدفتر"
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    # --- derived, written by services.recalculate ------------------------
    total_plies = models.PositiveIntegerField(default=0, verbose_name="إجمالي الراق")
    theoretical_pieces = models.PositiveIntegerField(default=0, verbose_name="القطع النظرية")
    total_roll_length_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name="إجمالي أطوال الأتواب"
    )
    total_remnant_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name="إجمالي البواقي"
    )
    consumed_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name="القماش المستهلك"
    )
    fabric_shortage_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"), verbose_name="عجز القماش"
    )
    expected_metrage = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("0"), verbose_name="الميتراج المتوقع"
    )
    real_metrage = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True, verbose_name="الميتراج الحقيقي"
    )
    deviation_pct = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="انحراف الميتراج %"
    )
    has_shortage = models.BooleanField(default=False, verbose_name="فيها عجز")
    # V4 drift: at least one roll's length does not match plies x lay length
    # plus remnant. A flag, not a block — see validators.check_v4_roll_arithmetic.
    has_length_mismatch = models.BooleanField(
        default=False, verbose_name="فيها فرق في الأطوال"
    )

    # --- audit -----------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت القفل")
    closed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_lays",
        verbose_name="قفلها",
    )
    # Set by the offline-first mobile screen so a retried sync does not create
    # the same lay twice.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        verbose_name = "فرشة"
        verbose_name_plural = "الفرشات"
        ordering = ["-start_date", "-id"]
        indexes = [
            # The date-intersection filter, the single most common query.
            models.Index(fields=["start_date", "end_date"], name="lay_period_idx"),
            models.Index(fields=["status", "end_date"], name="lay_status_end_idx"),
            models.Index(fields=["team_leader", "start_date"], name="lay_leader_idx"),
            models.Index(fields=["bank", "start_date"], name="lay_bank_idx"),
            models.Index(fields=["garment_model", "start_date"], name="lay_model_idx"),
            models.Index(fields=["has_shortage"], name="lay_shortage_idx"),
            models.Index(fields=["has_length_mismatch"], name="lay_length_mismatch_idx"),
            models.Index(fields=["is_backfill"], name="lay_backfill_idx"),
            models.Index(fields=["deviation_pct"], name="lay_deviation_idx"),
            models.Index(fields=["real_metrage"], name="lay_real_metrage_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="lay_end_after_start",
            ),
        ]

    def __str__(self):
        return f"فرشة {self.pk} · {self.garment_model_id} · {self.start_date}"

    @property
    def working_days(self) -> int:
        """Calendar days the lay spans, both ends included."""
        return (self.end_date - self.start_date).days + 1

    @property
    def is_multi_day(self) -> bool:
        return self.end_date > self.start_date

    @property
    def is_editable(self) -> bool:
        return self.status == self.STATUS_OPEN

    def clean(self):
        if self.start_date and not self.end_date:
            self.end_date = self.start_date
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": ValidationError(
                    "تاريخ النهاية قبل تاريخ البداية", code="date_order"
                )}
            )

    def save(self, *args, **kwargs):
        if self.start_date and not self.end_date:
            self.end_date = self.start_date
        super().save(*args, **kwargs)


class LaySizeBreakdown(models.Model):
    """How one ply splits across sizes, and what the count found per size.

    A snapshot: generated from the lay's SizeSet but editable per lay, so
    changing the model's default set never rewrites a closed lay.
    """

    lay = models.ForeignKey(Lay, on_delete=models.CASCADE, related_name="size_breakdown")
    size = models.CharField(max_length=20, verbose_name="المقاس")
    pieces_in_ply = models.PositiveIntegerField(verbose_name="قطع في الراق")
    actual_pieces = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="القطع الفعلية"
    )
    is_manually_adjusted = models.BooleanField(default=False, verbose_name="اتعدّل يدوي")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")

    class Meta:
        verbose_name = "مقاس في الفرشة"
        verbose_name_plural = "مقاسات الفرشة"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["lay", "size"], name="uniq_lay_size"),
        ]
        indexes = [models.Index(fields=["size"], name="breakdown_size_idx")]

    def __str__(self):
        return f"{self.size} × {self.pieces_in_ply}"

    @property
    def theoretical_pieces(self) -> int:
        """This size's share of the whole lay: pieces in a ply × total plies."""
        return self.pieces_in_ply * self.lay.total_plies


class LayLine(models.Model):
    """One roll laid onto the spread — one notebook row.

    There is no fabric-roll table in this phase (SRS 4.3), so the roll is
    identified by the text on its ticket. `roll_ref` is deliberately a plain
    integer, not a FK: it becomes one by migration when stock arrives.
    """

    ACTION_SPLICE = "splice"
    ACTION_NEW_ROLL = "new_roll"
    ACTION_STORED = "stored"
    ROLL_END_CHOICES = (
        (ACTION_SPLICE, "وصل"),
        (ACTION_NEW_ROLL, "توب جديد"),
        (ACTION_STORED, "اتخزن"),
    )

    DISPOSITION_WASTE = "waste"
    DISPOSITION_USABLE = "usable"
    DISPOSITION_CHOICES = ((DISPOSITION_WASTE, "هالك"), (DISPOSITION_USABLE, "صالح"))

    lay = models.ForeignKey(Lay, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField(verbose_name="رقم السطر")

    # Roll identity, as text from the ticket (SRS 4.3.1).
    roll_ref = models.PositiveIntegerField(null=True, blank=True, verbose_name="رقم التوب في المخزون")
    article = models.CharField(max_length=100, blank=True, verbose_name="الخامة")
    lot_no = models.CharField(max_length=50, blank=True, verbose_name="رقم اللوط")
    roll_no = models.CharField(max_length=50, blank=True, verbose_name="رقم التوب")
    barcode = models.CharField(max_length=100, blank=True, verbose_name="الباركود")
    ticket_image = models.ImageField(
        upload_to=lay_image_path, null=True, blank=True, verbose_name="صورة التيكت"
    )
    ticket_data = models.JSONField(default=dict, blank=True, verbose_name="بيانات التيكت")

    # Measurements.
    roll_length_m = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name="طول التوب (م)"
    )
    plies = models.PositiveIntegerField(verbose_name="الراق")
    remnant_m = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0"), verbose_name="الباقي (م)"
    )
    width_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="عرض التوب (سم)"
    )
    net_weight_kg = models.DecimalField(
        max_digits=7, decimal_places=3, null=True, blank=True, verbose_name="الوزن الصافي (كجم)"
    )

    shade_note = models.CharField(max_length=100, blank=True, verbose_name="توصيف اللون")
    roll_end_action = models.CharField(
        max_length=10,
        choices=ROLL_END_CHOICES,
        default=ACTION_NEW_ROLL,
        verbose_name="تصرّف نهاية التوب",
    )
    remnant_disposition = models.CharField(
        max_length=10, choices=DISPOSITION_CHOICES, blank=True, verbose_name="تصنيف الباقي"
    )
    # Quick mode collapses the whole spread into one synthetic row.
    is_aggregate = models.BooleanField(default=False, verbose_name="سطر مجمّع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "سطر توب"
        verbose_name_plural = "سطور الأتواب"
        ordering = ["line_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["lay", "line_no"], name="uniq_lay_line_no"),
            models.CheckConstraint(condition=models.Q(plies__gt=0), name="line_plies_positive"),
            models.CheckConstraint(
                condition=models.Q(roll_length_m__gt=0), name="line_length_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["article"], name="line_article_idx"),
            models.Index(fields=["lot_no"], name="line_lot_idx"),
        ]

    def __str__(self):
        return f"سطر {self.line_no} · {self.roll_length_m} م × {self.plies} راق"

    @property
    def has_splice(self) -> bool:
        """This row shares its last ply with the row that continues it."""
        return self.roll_end_action == self.ACTION_SPLICE

    @property
    def expected_roll_length_m(self) -> Decimal:
        """What the roll should have measured: plies × lay length + remnant."""
        return self.plies * self.lay.lay_length_m + self.remnant_m

    def classify_remnant(self, threshold: Decimal = None) -> str:
        """Waste below the threshold, usable at or above it (SRS 5.4)."""
        if threshold is None:
            threshold = CuttingSettings.get_solo().remnant_waste_threshold_m
        if self.remnant_m <= 0:
            return ""
        return self.DISPOSITION_WASTE if self.remnant_m < threshold else self.DISPOSITION_USABLE

    def clean(self):
        """V2 and V3. Tagged with their SRS codes so the API can pass the rule
        number straight through to the screen."""
        errors = {}
        if self.plies is not None and self.plies <= 0:
            errors["plies"] = ValidationError("الراق لازم يكون أكبر من صفر", code="V2")
        if self.roll_length_m is not None and self.roll_length_m <= 0:
            errors["roll_length_m"] = ValidationError(
                "طول التوب لازم يكون أكبر من صفر", code="V2"
            )
        if self.remnant_m is not None and self.remnant_m < 0:
            errors["remnant_m"] = ValidationError("الباقي ماينفعش يكون بالسالب", code="V2")
        # V3 — needs the parent's lay length.
        elif self.remnant_m is not None and self.lay_id:
            if self.remnant_m >= self.lay.lay_length_m:
                errors["remnant_m"] = ValidationError(
                    "الباقي أكبر من طول الفرشة — كان ينفع راق زيادة", code="V3"
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.remnant_disposition:
            self.remnant_disposition = self.classify_remnant()
        super().save(*args, **kwargs)


class LayOutput(models.Model):
    """The count after numbering — what actually came off the table."""

    lay = models.OneToOneField(Lay, on_delete=models.CASCADE, related_name="output")
    actual_pieces = models.PositiveIntegerField(verbose_name="القطع السليمة")
    rejected_pieces = models.PositiveIntegerField(default=0, verbose_name="التالف")
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="recorded_outputs", verbose_name="سجّلها"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, verbose_name="سبب الفرق")

    class Meta:
        verbose_name = "قطع فعلية"
        verbose_name_plural = "القطع الفعلية"

    def __str__(self):
        return f"فرشة {self.lay_id}: {self.actual_pieces} قطعة"

    @property
    def pieces_loss(self) -> int:
        """Theoretical minus actual. Negative means more came off than expected."""
        return self.lay.theoretical_pieces - self.actual_pieces


class RemnantLog(models.Model):
    """Informational record of leftover fabric — no balance, no stock movement.

    Kept so we can answer "how many metres went to waste this month" before
    there is any inventory, and so those metres become real balances when
    inventory arrives (SRS 4.3.1).
    """

    lay_line = models.OneToOneField(LayLine, on_delete=models.CASCADE, related_name="remnant_log")
    length_m = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="الطول (م)")
    shade_note = models.CharField(max_length=100, blank=True, verbose_name="توصيف اللون")
    lot_no = models.CharField(max_length=50, blank=True, verbose_name="رقم اللوط")
    article = models.CharField(max_length=100, blank=True, verbose_name="الخامة")
    DISPOSITION_WASTE = LayLine.DISPOSITION_WASTE
    DISPOSITION_USABLE = LayLine.DISPOSITION_USABLE

    disposition = models.CharField(
        max_length=10, choices=LayLine.DISPOSITION_CHOICES, verbose_name="التصنيف"
    )
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "باقي مسجّل"
        verbose_name_plural = "سجل البواقي"
        ordering = ["-logged_at"]
        indexes = [
            models.Index(fields=["disposition"], name="remnant_disposition_idx"),
            models.Index(fields=["article"], name="remnant_article_idx"),
        ]

    def __str__(self):
        return f"{self.length_m} م ({self.get_disposition_display()})"


class SavedFilter(models.Model):
    """A search the supervisor uses often, kept by name (SRS 7.1.1).

    The whole query string is stored verbatim rather than parsed into columns:
    the list page already puts its state in the URL, so saving is just keeping
    that string, and a new filter never needs a migration here.
    """

    name = models.CharField(max_length=100, verbose_name="اسم البحث")
    query = models.TextField(blank=True, verbose_name="نص البحث")
    params = models.TextField(blank=True, verbose_name="باقي الفلاتر")
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="cutting_saved_filters"
    )
    # Shared filters show for everyone; the rest only for whoever made them.
    is_shared = models.BooleanField(default=False, verbose_name="مشترك")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "بحث محفوظ"
        verbose_name_plural = "البحثات المحفوظة"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_saved_filter_name"),
        ]

    def __str__(self):
        return self.name


class Notification(models.Model):
    """An in-system alert (SRS 11.1), and the queue the daily email digest
    draws from.

    One row per (lay, kind, recipient): the same shortage must not pile up a
    new alert every time the lay is recalculated.
    """

    KIND_SHORTAGE = "shortage"
    KIND_PIECES_LOSS = "pieces_loss"
    KIND_AWAITING_COUNT = "awaiting_count"
    KIND_CHOICES = (
        (KIND_SHORTAGE, "عجز في القماش"),
        (KIND_PIECES_LOSS, "فاقد في القطع"),
        (KIND_AWAITING_COUNT, "مستنية ترقيم"),
    )

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="cutting_notifications"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name="النوع")
    lay = models.ForeignKey(
        Lay, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True
    )
    title = models.CharField(max_length=200, verbose_name="العنوان")
    body = models.TextField(blank=True, verbose_name="التفاصيل")
    is_read = models.BooleanField(default=False, verbose_name="مقروء")
    read_at = models.DateTimeField(null=True, blank=True)
    # Null until the daily digest has carried it. Keeps the digest from
    # sending the same alert twice, and lets it batch a whole day into one
    # message instead of an email per lay (SRS 11.1).
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تنبيه"
        verbose_name_plural = "التنبيهات"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lay", "kind", "recipient"], name="uniq_lay_notification"
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "is_read"], name="notif_recipient_idx"),
            models.Index(fields=["emailed_at"], name="notif_emailed_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.title}"


class LayAudit(models.Model):
    """Who changed what after the lay was closed, and why (SRS section 10)."""

    lay = models.ForeignKey(Lay, on_delete=models.CASCADE, related_name="audit_entries")
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="lay_audit_entries"
    )
    at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=30, verbose_name="الحدث")
    field = models.CharField(max_length=50, blank=True, verbose_name="الحقل")
    old_value = models.TextField(blank=True, verbose_name="القيمة القديمة")
    new_value = models.TextField(blank=True, verbose_name="القيمة الجديدة")
    reason = models.TextField(blank=True, verbose_name="السبب")

    class Meta:
        verbose_name = "سجل نشاط"
        verbose_name_plural = "سجل النشاط"
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["lay", "at"], name="audit_lay_at_idx")]

    def __str__(self):
        return f"{self.action} · فرشة {self.lay_id}"
