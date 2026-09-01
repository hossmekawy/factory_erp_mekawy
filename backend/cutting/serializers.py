"""DRF serializers for the cutting module.

Deliberately thin. They shape JSON and nothing else: no arithmetic (that is
`services`) and no business rules of their own (those are model `clean()` and
`validators`), so the admin, a shell session and the API all hit the same
walls. `ModelCleanMixin` is what wires the model's rules into the API.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from hr.models import Employee

from . import exceptions, services
from . import sizes as size_utils
from .models import (
    Bank,
    Category,
    CuttingSettings,
    GarmentModel,
    Lay,
    LayAudit,
    LayLine,
    LayOutput,
    LayShadeBreakdown,
    LaySizeBreakdown,
    Notification,
    RemnantLog,
    SavedFilter,
    SizeSet,
)


class ModelCleanMixin:
    """Run the model's own `clean()` during serializer validation.

    Without this the API would be the one write path that skips the rules the
    admin and the shell obey.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if instance is None:
            instance = self.Meta.model()
        else:
            # Work on a copy: validation must not mutate the stored row.
            instance = self.Meta.model.objects.get(pk=instance.pk)
        for field, value in attrs.items():
            if not isinstance(value, (list, tuple)):
                setattr(instance, field, value)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            exceptions.raise_as_drf(exc)
        return attrs


# --- catalogues ----------------------------------------------------------

class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ["id", "code", "name", "is_active"]


class SizeSetSerializer(ModelCleanMixin, serializers.ModelSerializer):
    parsed = serializers.SerializerMethodField()

    category_label = serializers.CharField(source="category.name", read_only=True,
                                           default="")

    class Meta:
        model = SizeSet
        fields = ["id", "name", "sizes_raw", "total_pieces", "parsed", "category",
                  "category_label", "is_preset", "is_active", "created_at"]
        read_only_fields = ["total_pieces"]  # always derived from sizes_raw

    def get_parsed(self, obj):
        try:
            return [{"size": s, "pieces_in_ply": n} for s, n in obj.parsed()]
        except size_utils.SizeParseError:
            return []


class CategorySerializer(serializers.ModelSerializer):
    model_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "notes", "order", "is_active", "model_count", "created_at"]


class GarmentModelSerializer(serializers.ModelSerializer):
    default_size_set_detail = SizeSetSerializer(source="default_size_set", read_only=True)
    category_label = serializers.CharField(source="category.name", read_only=True, default="")
    lay_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = GarmentModel
        fields = [
            "id", "code", "name", "category", "category_label",
            "default_size_set", "default_size_set_detail", "image", "notes",
            "is_active", "lay_count", "created_at",
        ]
        # Generated on save, never accepted from the client.
        read_only_fields = ["code"]
        extra_kwargs = {
            # Every model must carry a section: it is the axis the reports are
            # read along, and one without it drops out of every filter.
            "category": {"required": True, "allow_null": False},
        }


class CuttingSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuttingSettings
        fields = [
            "id", "fabric_tolerance_pct", "pieces_tolerance_pct",
            "remnant_waste_threshold_m", "notify_emails",
            "default_bank", "default_team_leader", "updated_at",
        ]


class TeamLeaderSerializer(serializers.ModelSerializer):
    """An employee as the lay screen needs them, plus whether the fingerprint
    device saw them inside the lay's dates."""

    was_present = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Employee
        fields = ["id", "employee_code", "full_name", "job_title", "is_team_leader", "was_present"]


# --- lay parts -----------------------------------------------------------

class NextLineNumber:
    """Default for `line_no`: the next free number on the lay being written to.

    A default rather than something computed in `validate()`, because the
    unique-together validator on (lay, line_no) runs first and reports the
    field as missing before `validate()` is ever reached. The client sends what
    it read off the notebook; the position in the table is ours.
    """

    requires_context = True

    def __call__(self, field):
        serializer = field.parent
        lay_id = None
        initial = getattr(serializer, "initial_data", None)
        if isinstance(initial, dict):
            lay_id = initial.get("lay")
        if not lay_id:
            lay_id = getattr(serializer.context.get("lay"), "pk", None)
        if not lay_id:
            return 1
        last = (
            LayLine.objects.filter(lay_id=lay_id)
            .order_by("-line_no")
            .values_list("line_no", flat=True)
            .first()
        )
        return (last or 0) + 1


class LayLineSerializer(ModelCleanMixin, serializers.ModelSerializer):
    remnant_disposition_label = serializers.CharField(
        source="get_remnant_disposition_display", read_only=True
    )
    roll_end_action_label = serializers.CharField(
        source="get_roll_end_action_display", read_only=True
    )
    has_splice = serializers.BooleanField(read_only=True)
    line_no = serializers.IntegerField(required=False, default=NextLineNumber())

    class Meta:
        model = LayLine
        fields = [
            "id", "lay", "line_no", "roll_ref", "article", "lot_no", "roll_no",
            "barcode", "roll_length_m", "plies",
            "remnant_m", "shade_note",
            "roll_end_action", "roll_end_action_label", "remnant_disposition",
            "remnant_disposition_label", "has_splice", "is_aggregate", "notes",
        ]
        read_only_fields = ["remnant_disposition"]  # classified by the threshold

    def validate(self, attrs):
        # V3 compares against the parent's lay length, so the parent has to be
        # attached before clean() runs.
        if self.instance is None and not attrs.get("lay"):
            lay = self.context.get("lay")
            if lay is not None:
                attrs["lay"] = lay
        return super().validate(attrs)


class LayLineNestedSerializer(LayLineSerializer):
    """Lines posted inside a lay payload — the parent is not known yet."""

    # The phone posts the rows in notebook order; create() numbers them.
    line_no = serializers.IntegerField(required=False, allow_null=True, default=None)

    class Meta(LayLineSerializer.Meta):
        fields = [f for f in LayLineSerializer.Meta.fields if f != "lay"]

    def validate(self, attrs):
        return serializers.ModelSerializer.validate(self, attrs)


class LaySizeBreakdownSerializer(serializers.ModelSerializer):
    theoretical_pieces = serializers.IntegerField(read_only=True)

    class Meta:
        model = LaySizeBreakdown
        fields = [
            "id", "size", "pieces_in_ply", "actual_pieces", "theoretical_pieces",
            "is_manually_adjusted", "order",
        ]


class LayShadeBreakdownSerializer(serializers.ModelSerializer):
    pieces = serializers.IntegerField(read_only=True)
    pct = serializers.FloatField(read_only=True)

    class Meta:
        model = LayShadeBreakdown
        fields = ["id", "shade", "plies", "pieces", "pct", "is_manual", "order"]


class LayOutputSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True)
    pieces_loss = serializers.IntegerField(read_only=True)

    class Meta:
        model = LayOutput
        fields = [
            "id", "actual_pieces", "rejected_pieces", "pieces_loss",
            "recorded_by", "recorded_by_name", "recorded_at", "notes",
        ]
        read_only_fields = ["recorded_by", "recorded_at"]


class RecordOutputSerializer(serializers.Serializer):
    """Body of POST /lays/{id}/output/ — the numbering screen."""

    actual_pieces = serializers.IntegerField(min_value=0)
    rejected_pieces = serializers.IntegerField(min_value=0, required=False, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    # {"32": 120, "34": 118} — omit for the automatic largest-remainder split.
    manual_distribution = serializers.DictField(
        child=serializers.IntegerField(min_value=0), required=False, allow_null=True
    )


class CloseLaySerializer(serializers.Serializer):
    """Body of POST /lays/{id}/close/. A reason is what lets warnings through.

    The count may ride along. Numbering is usually a separate job done later,
    but when the pieces are already known there is no sense making the
    supervisor come back to a second screen for two numbers — and doing it in
    the one request means a lay is never left closed-but-half-counted.
    """

    reason = serializers.CharField(required=False, allow_blank=True, default="")
    actual_pieces = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    rejected_pieces = serializers.IntegerField(min_value=0, required=False, default=0)
    output_notes = serializers.CharField(required=False, allow_blank=True, default="")


class LayAuditSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = LayAudit
        fields = ["id", "action", "field", "old_value", "new_value", "reason",
                  "user", "user_name", "at"]


class NotificationSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    lay_code = serializers.CharField(source="lay.garment_model.code", read_only=True,
                                     default="")

    class Meta:
        model = Notification
        fields = ["id", "kind", "kind_label", "lay", "lay_code", "title", "body",
                  "is_read", "read_at", "created_at"]
        read_only_fields = fields


class SavedFilterSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = SavedFilter
        fields = ["id", "name", "query", "params", "is_shared", "owner",
                  "owner_name", "created_at"]
        read_only_fields = ["owner"]


class RemnantLogSerializer(serializers.ModelSerializer):
    lay = serializers.IntegerField(source="lay_line.lay_id", read_only=True)
    disposition_label = serializers.CharField(source="get_disposition_display", read_only=True)

    class Meta:
        model = RemnantLog
        fields = [
            "id", "lay", "lay_line", "length_m", "shade_note", "lot_no",
            "article", "disposition", "disposition_label", "logged_at",
        ]


# --- the lay itself ------------------------------------------------------

DERIVED_FIELDS = [
    "total_plies", "theoretical_pieces", "total_roll_length_m", "total_remnant_m",
    "consumed_m", "fabric_shortage_m", "expected_metrage", "real_metrage",
    "deviation_pct", "has_shortage", "has_length_mismatch", "has_splice",
]


class LayListSerializer(serializers.ModelSerializer):
    """The list view (SRS 7.1) — flat, no nested queries per row."""

    garment_model_code = serializers.CharField(source="garment_model.code", read_only=True)
    garment_model_name = serializers.CharField(source="garment_model.name", read_only=True)
    category = serializers.CharField(source="garment_model.category.name",
                                     read_only=True, default="")
    bank_name = serializers.CharField(source="bank.name", read_only=True)
    team_leader_name = serializers.CharField(source="team_leader.full_name", read_only=True)
    sizes_summary = serializers.SerializerMethodField()
    actual_pieces = serializers.IntegerField(source="output.actual_pieces", read_only=True,
                                             default=None)
    working_days = serializers.IntegerField(read_only=True)
    is_multi_day = serializers.BooleanField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    has_sheet_image = serializers.SerializerMethodField()

    class Meta:
        model = Lay
        fields = [
            "id", "start_date", "end_date", "working_days", "is_multi_day",
            "code", "garment_model", "garment_model_code", "garment_model_name", "category",
            "bank", "bank_name", "team_leader", "team_leader_name",
            "lay_length_m", "lay_width_cm", "pieces_per_ply", "sizes_summary",
            "actual_pieces", "status", "status_label", "entry_mode",
            "is_backfill", "has_sheet_image", *DERIVED_FIELDS,
        ]

    def get_sizes_summary(self, obj):
        return [b.size for b in obj.size_breakdown.all()]

    def get_has_sheet_image(self, obj):
        return bool(obj.sheet_image)


class LaySerializer(ModelCleanMixin, serializers.ModelSerializer):
    """Detail and write.

    The mobile screen posts one payload: the header, `sizes_raw`, and the
    lines. `pieces_per_ply` is always derived from the sizes and never taken
    from the client — V6 exists precisely because those two can disagree.
    """

    lines = LayLineNestedSerializer(many=True, required=False)
    size_breakdown = LaySizeBreakdownSerializer(many=True, read_only=True)
    shade_breakdown = LayShadeBreakdownSerializer(many=True, read_only=True)
    # Quick mode only: [{"shade": "أسود", "plies": 40}]. Optional throughout —
    # an empty list clears it and the lay closes exactly as before.
    shade_entries = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )
    output = LayOutputSerializer(read_only=True)
    audit_entries = LayAuditSerializer(many=True, read_only=True)

    # Optional in: the model fills it from start_date for a same-day lay.
    end_date = serializers.DateField(required=False)
    sizes_raw = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # Mandatory when editing a lay that is already closed (SRS section 3). The
    # check is in validate(), because whether it is required depends on the row
    # being edited, not on the payload.
    edit_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # The cutting-run code. Unique, with its own message: the default one is
    # English and names the column.
    code = serializers.CharField(
        max_length=30,
        validators=[
            UniqueValidator(
                queryset=Lay.objects.all(),
                message="كود القصة ده مستخدم في قصة تانية",
            )
        ],
    )
    garment_model_detail = GarmentModelSerializer(source="garment_model", read_only=True)
    bank_detail = BankSerializer(source="bank", read_only=True)
    team_leader_detail = TeamLeaderSerializer(source="team_leader", read_only=True)
    entered_by_name = serializers.CharField(source="entered_by.username", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    working_days = serializers.IntegerField(read_only=True)
    is_multi_day = serializers.BooleanField(read_only=True)

    class Meta:
        model = Lay
        fields = [
            "id", "code", "start_date", "end_date", "working_days", "is_multi_day",
            "bank", "bank_detail", "garment_model", "garment_model_detail",
            "size_set", "team_leader", "team_leader_detail", "team_members",
            "entered_by", "entered_by_name", "lay_width_cm",
            "lay_length_m", "pieces_per_ply", "entry_mode", "is_backfill",
            "sheet_image", "notes", "status", "status_label", "client_uuid",
            "lines", "size_breakdown", "shade_breakdown", "output", "audit_entries",
            "sizes_raw", "edit_reason", "shade_entries",
            "created_at", "updated_at", "closed_at", "closed_by",
            *DERIVED_FIELDS,
        ]
        read_only_fields = [
            "entered_by", "status", "closed_at", "closed_by",
            "pieces_per_ply", *DERIVED_FIELDS,
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        # SRS 3: an edit after closing needs a reason, and the reason is what
        # gets written into the activity log.
        if self.instance is not None and self.instance.status != Lay.STATUS_OPEN:
            changing = {
                f for f, v in attrs.items()
                if f not in ("edit_reason", "shade_entries")
                and getattr(self.instance, f, None) != v
            }
            if changing and not (attrs.get("edit_reason") or "").strip():
                raise serializers.ValidationError({
                    "detail": "القصة مقفولة — لازم سبب للتعديل",
                    "issues": [{
                        "code": "edit_reason", "level": "error",
                        "message": "القصة مقفولة. اكتب سبب التعديل — بيتسجّل في سجل النشاط.",
                        "field": "edit_reason", "line_no": None,
                    }],
                })

        if self.instance is None:
            has_sizes = attrs.get("sizes_raw") or attrs.get("size_set")
            if not has_sizes:
                raise serializers.ValidationError(
                    {
                        "detail": "البيانات مش مظبوطة",
                        "issues": [{
                            "code": "V6", "level": "error",
                            "message": "لازم تكتب المقاسات أو تختار طقم مقاسات",
                            "field": "sizes_raw", "line_no": None,
                        }],
                    }
                )
        return attrs

    def _resolve_size_set(self, validated):
        """Turn free size text into a SizeSet the lay can snapshot from."""
        raw = validated.pop("sizes_raw", None)
        if not raw:
            return validated.get("size_set")
        try:
            pairs = size_utils.parse_sizes(raw)
        except size_utils.SizeParseError as exc:
            raise serializers.ValidationError(
                {
                    "detail": "المقاسات مش مقروءة",
                    "issues": [{
                        "code": "sizes_unreadable", "level": "error",
                        "message": str(exc), "field": "sizes_raw", "line_no": None,
                    }],
                }
            )
        canonical = size_utils.format_sizes(pairs)
        # is_preset stays False: this row exists only so the lay has a
        # breakdown to snapshot from, not as something to offer next time.
        size_set, _created = SizeSet.objects.get_or_create(
            sizes_raw=canonical, is_preset=False, defaults={"name": canonical}
        )
        return size_set

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        shade_entries = validated_data.pop("shade_entries", None)
        validated_data.pop("edit_reason", None)
        members = validated_data.pop("team_members", [])
        size_set = self._resolve_size_set(validated_data)
        validated_data["size_set"] = size_set
        # A placeholder: sync_breakdown_from_size_set overwrites it immediately.
        validated_data["pieces_per_ply"] = size_set.total_pieces

        lay = Lay.objects.create(**validated_data)
        if members:
            lay.team_members.set(members)
        services.sync_breakdown_from_size_set(lay, size_set)

        for i, line in enumerate(lines_data, start=1):
            # `or i` not setdefault: the nested serializer sends line_no=None
            # explicitly, and a key that is present but null defeats setdefault.
            line["line_no"] = line.get("line_no") or i
            LayLine.objects.create(lay=lay, **line)
        services.recalculate(lay)
        if shade_entries is not None and lay.entry_mode == Lay.MODE_QUICK:
            services.set_shade_breakdown(lay, shade_entries)
        lay.refresh_from_db()
        return lay

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        shade_entries = validated_data.pop("shade_entries", None)
        reason = validated_data.pop("edit_reason", "")
        members = validated_data.pop("team_members", None)
        size_set = self._resolve_size_set(validated_data)

        was_closed = instance.status != Lay.STATUS_OPEN
        changed = {
            f: (getattr(instance, f), v)
            for f, v in validated_data.items()
            if getattr(instance, f, None) != v
        }

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if size_set is not None and size_set != instance.size_set:
            instance.size_set = size_set
        instance.save()

        if members is not None:
            instance.team_members.set(members)
        if size_set is not None:
            services.sync_breakdown_from_size_set(instance, size_set)

        if lines_data is not None:
            instance.lines.all().delete()
            for i, line in enumerate(lines_data, start=1):
                line["line_no"] = line.get("line_no") or i
                LayLine.objects.create(lay=instance, **line)

        services.recalculate(instance)
        if shade_entries is not None and instance.entry_mode == Lay.MODE_QUICK:
            services.set_shade_breakdown(instance, shade_entries)

        if was_closed:
            # SRS section 3: an edit after closing is recorded, field by field.
            for field, (old, new) in changed.items():
                LayAudit.objects.create(
                    lay=instance,
                    user=self.context["request"].user,
                    action="edit_after_close",
                    field=field,
                    old_value=str(old),
                    new_value=str(new),
                    reason=reason,
                )
        instance.refresh_from_db()
        return instance
