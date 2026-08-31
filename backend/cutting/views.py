from django.db.models import Count, Sum
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .filters import CuttingOrderFilter
from .models import CuttingOrder, FabricRoll, Marker, MarkerSize
from .ocr import ocr_label_image
from .permissions import CanTouchCutting, IsCuttingStaff, visible_cuttings
from .reports import build_cutting_report, cutting_report_xlsx
from .reports_pdf import build_cutting_pdf
from .serializers import (
    CuttingOrderDetailSerializer,
    CuttingOrderListSerializer,
    FabricRollSerializer,
    MarkerSerializer,
)
from .services import compute_summary


class CuttingOrderViewSet(viewsets.ModelViewSet):
    queryset = CuttingOrder.objects.all()
    permission_classes = [IsCuttingStaff, CanTouchCutting]
    filterset_class = CuttingOrderFilter
    search_fields = ["code", "model_name", "color", "production_order_no"]

    def get_queryset(self):
        qs = visible_cuttings(self.request.user, CuttingOrder.objects.all())
        if self.action == "list":
            qs = qs.select_related("created_by").annotate(
                rolls_count=Count("rolls", distinct=True),
                rolls_total=Sum("rolls__length"),
            )
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return CuttingOrderListSerializer
        return CuttingOrderDetailSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # ---- markers -------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="markers")
    def add_marker(self, request, pk=None):
        cutting = self.get_object()
        ser = MarkerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(cutting=cutting)
        return Response(
            {"marker": ser.data, "summary": compute_summary(cutting)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["patch", "delete"], url_path=r"markers/(?P<marker_id>\d+)")
    def marker_detail(self, request, pk=None, marker_id=None):
        cutting = self.get_object()
        try:
            marker = cutting.markers.get(pk=marker_id)
        except Marker.DoesNotExist:
            return Response({"detail": "الفرشة غير موجودة"}, status=404)
        if request.method == "DELETE":
            marker.delete()
            return Response({"summary": compute_summary(cutting)})
        ser = MarkerSerializer(marker, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"marker": ser.data, "summary": compute_summary(cutting)})

    # ---- rolls (per-roll autosave) --------------------------------------

    @action(detail=True, methods=["post"], url_path="rolls")
    def add_roll(self, request, pk=None):
        cutting = self.get_object()
        ser = FabricRollSerializer(data=request.data, context={"cutting": cutting})
        ser.is_valid(raise_exception=True)
        ser.save(cutting=cutting)
        return Response(
            {"roll": ser.data, "summary": compute_summary(cutting)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["patch", "delete"], url_path=r"rolls/(?P<roll_id>\d+)")
    def roll_detail(self, request, pk=None, roll_id=None):
        cutting = self.get_object()
        try:
            roll = cutting.rolls.get(pk=roll_id)
        except FabricRoll.DoesNotExist:
            return Response({"detail": "التوب غير موجود"}, status=404)
        if request.method == "DELETE":
            roll.delete()
            return Response({"summary": compute_summary(cutting)})
        ser = FabricRollSerializer(
            roll, data=request.data, partial=True, context={"cutting": cutting}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"roll": ser.data, "summary": compute_summary(cutting)})

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        return Response(compute_summary(self.get_object()))


@api_view(["GET"])
@permission_classes([IsCuttingStaff])
def size_suggestions(request):
    """Previously used size labels, most frequent first — for autocomplete."""
    labels = (
        MarkerSize.objects.values("label")
        .annotate(n=Count("id"))
        .order_by("-n", "label")
        .values_list("label", flat=True)[:50]
    )
    return Response(list(labels))


@api_view(["POST"])
@permission_classes([IsCuttingStaff])
def ocr_label(request):
    upload = request.FILES.get("image")
    if not upload:
        return Response({"detail": "أرفق صورة الليبل"}, status=400)
    if upload.size > 10 * 1024 * 1024:
        return Response({"detail": "الصورة كبيرة جداً (الحد الأقصى 10 ميجا)"}, status=400)
    try:
        result = ocr_label_image(upload)
    except Exception:
        return Response({"detail": "تعذر قراءة الصورة — جرّب صورة أوضح"}, status=400)
    return Response(result)


def _filtered_report(request):
    qs = visible_cuttings(request.user, CuttingOrder.objects.all())
    f = CuttingOrderFilter(request.query_params, queryset=qs)
    return build_cutting_report(f.qs.distinct(), dict(request.query_params.items()))


@api_view(["GET"])
@permission_classes([IsCuttingStaff])
def cutting_report(request):
    return Response(_filtered_report(request))


@api_view(["GET"])
@permission_classes([IsCuttingStaff])
def cutting_report_export(request):
    buf = cutting_report_xlsx(_filtered_report(request))
    return FileResponse(
        buf,
        as_attachment=True,
        filename="cutting-report.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@api_view(["GET"])
@permission_classes([IsCuttingStaff])
def cutting_report_pdf(request):
    size = "a5" if request.query_params.get("size", "a4").lower() == "a5" else "a4"
    buf = build_cutting_pdf(_filtered_report(request), size)
    return FileResponse(
        buf, as_attachment=True, filename=f"cutting-report-{size}.pdf",
        content_type="application/pdf",
    )
