from rest_framework import serializers

from .models import CuttingOrder, FabricRoll, Marker, MarkerSize
from .services import compute_summary

MAX_LENGTH_M = 2000


def _positive(value, label):
    if value is not None and value <= 0:
        raise serializers.ValidationError(f"{label} يجب أن يكون أكبر من صفر")
    return value


class MarkerSizeSerializer(serializers.ModelSerializer):
    total_pieces = serializers.IntegerField(read_only=True)

    class Meta:
        model = MarkerSize
        fields = ["id", "label", "ratio", "total_pieces"]

    def validate_label(self, v):
        v = v.strip()
        if not v:
            raise serializers.ValidationError("المقاس لا يمكن أن يكون فارغاً")
        return v

    def validate_ratio(self, v):
        return _positive(v, "عدد القطع في الراقة")


class MarkerSerializer(serializers.ModelSerializer):
    sizes = MarkerSizeSerializer(many=True, required=False)
    pieces_per_lay = serializers.IntegerField(required=False, min_value=1)
    expected_metraj = serializers.SerializerMethodField()
    total_pieces = serializers.IntegerField(read_only=True)

    class Meta:
        model = Marker
        fields = [
            "id", "fabric_width", "marker_length", "min_top_length",
            "pieces_per_lay", "layers_count", "lays_count",
            "sizes", "expected_metraj", "total_pieces",
        ]

    def get_expected_metraj(self, obj):
        v = obj.expected_metraj
        return None if v is None else float(v)

    def validate_marker_length(self, v):
        _positive(v, "طول الفرشة")
        if v > MAX_LENGTH_M:
            raise serializers.ValidationError("طول الفرشة غير منطقي")
        return v

    def validate_lays_count(self, v):
        return _positive(v, "عدد الراقات")

    def validate(self, data):
        sizes = data.get("sizes")
        if sizes is not None:
            labels = [s["label"] for s in sizes]
            if len(labels) != len(set(labels)):
                raise serializers.ValidationError({"sizes": "يوجد مقاس مكرر"})
        has_sizes = sizes if sizes is not None else (
            self.instance and self.instance.sizes.exists()
        )
        has_ppl = data.get(
            "pieces_per_lay", getattr(self.instance, "pieces_per_lay", None)
        )
        if not has_sizes and not has_ppl:
            raise serializers.ValidationError(
                {"pieces_per_lay": "أدخل المقاسات أو عدد القطع في الراقة"}
            )
        # sizes always win: pieces_per_lay = sum of ratios
        if sizes:
            data["pieces_per_lay"] = sum(s["ratio"] for s in sizes)
        return data

    def _replace_sizes(self, marker, sizes):
        marker.sizes.all().delete()
        MarkerSize.objects.bulk_create(
            MarkerSize(marker=marker, **s) for s in sizes
        )

    def create(self, validated_data):
        sizes = validated_data.pop("sizes", None)
        marker = super().create(validated_data)
        if sizes:
            self._replace_sizes(marker, sizes)
        return marker

    def update(self, instance, validated_data):
        sizes = validated_data.pop("sizes", None)
        marker = super().update(instance, validated_data)
        if sizes is not None:
            self._replace_sizes(marker, sizes)
            if not sizes and not validated_data.get("pieces_per_lay"):
                pass  # cleared sizes but kept existing pieces_per_lay
        return marker


class FabricRollSerializer(serializers.ModelSerializer):
    expected_remaining = serializers.SerializerMethodField()
    remaining_diff = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = FabricRoll
        fields = [
            "id", "marker", "roll_number", "lot_number", "article_name", "color",
            "width", "length", "weight", "grade", "lays_used", "actual_remaining",
            "status", "status_display", "label_photo",
            "expected_remaining", "remaining_diff", "created_at",
        ]

    def get_expected_remaining(self, obj):
        v = obj.expected_remaining
        return None if v is None else float(v)

    def get_remaining_diff(self, obj):
        v = obj.remaining_diff
        return None if v is None else float(v)

    def validate_length(self, v):
        _positive(v, "الطول")
        if v > MAX_LENGTH_M:
            raise serializers.ValidationError("الطول غير منطقي")
        return v

    def validate_width(self, v):
        if v is not None and not (10 <= v <= 500):
            raise serializers.ValidationError("العرض غير منطقي (١٠–٥٠٠ سم)")
        return v

    def validate(self, data):
        cutting = self.context.get("cutting") or (self.instance and self.instance.cutting)

        length = data.get("length", getattr(self.instance, "length", None))
        remaining = data.get(
            "actual_remaining", getattr(self.instance, "actual_remaining", None)
        )
        if remaining is not None and length is not None and remaining > length:
            raise serializers.ValidationError(
                {"actual_remaining": "الباقي لا يمكن أن يكون أكبر من طول التوب"}
            )

        roll_number = data.get(
            "roll_number", getattr(self.instance, "roll_number", "")
        )
        if roll_number and cutting is not None:
            qs = FabricRoll.objects.filter(cutting=cutting, roll_number=roll_number)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"roll_number": "رقم التوب مكرر في نفس القصة"}
                )
        return data


class CuttingOrderListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    rolls_count = serializers.IntegerField(read_only=True)
    total_meters = serializers.SerializerMethodField()

    class Meta:
        model = CuttingOrder
        fields = [
            "id", "code", "model_name", "color", "production_order_no",
            "cutting_date", "created_by", "created_by_name",
            "rolls_count", "total_meters", "has_shortage",
        ]

    def get_created_by_name(self, obj):
        u = obj.created_by
        return u.first_name or u.username

    def get_total_meters(self, obj):
        # annotated by the viewset; fall back to summary math if absent
        v = getattr(obj, "rolls_total", None)
        if v is not None:
            return float(v)
        if obj.quick_total_meters is not None:
            return float(obj.quick_total_meters)
        return None


class CuttingOrderDetailSerializer(serializers.ModelSerializer):
    markers = MarkerSerializer(many=True, read_only=True)
    rolls = FabricRollSerializer(many=True, read_only=True)
    summary = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CuttingOrder
        fields = [
            "id", "code", "model_name", "color", "production_order_no",
            "cutting_date", "created_by", "created_by_name", "worksheet_photo",
            "quick_total_meters", "has_shortage", "shortage_quantity",
            "shortage_reason", "shortage_notes", "notes",
            "markers", "rolls", "summary", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by"]

    def get_summary(self, obj):
        return compute_summary(obj)

    def get_created_by_name(self, obj):
        u = obj.created_by
        return u.first_name or u.username

    def validate_code(self, v):
        qs = CuttingOrder.objects.filter(code=v)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("كود القصة مستخدم من قبل")
        return v

    def validate_quick_total_meters(self, v):
        if v is not None and v <= 0:
            raise serializers.ValidationError("إجمالي الأمتار يجب أن يكون أكبر من صفر")
        return v
