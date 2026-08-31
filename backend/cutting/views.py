"""ViewSets for the cutting module.

Thin by design: they authorise, shape the queryset, and hand off. Every
calculation is in `services` and every rule is in the models or `validators`,
so nothing here can drift from what the admin and the shell enforce.

Failures come back in one shape, carrying the SRS rule number — see
`exceptions.issues_payload`.
"""
import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.db.models import Avg, Count, Prefetch, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from hr.attendance import present_codes
from hr.models import Employee

from . import exceptions, filters, search, services
from . import sizes as size_utils
from . import validators
from .models import (
    Bank,
    CuttingSettings,
    GarmentModel,
    Lay,
    LayLine,
    RemnantLog,
    SavedFilter,
    SizeSet,
)
from .permissions import (
    CanAddToCatalogue,
    CanEditLays,
    CanManageCatalogue,
    CanViewCutting,
)
from .serializers import (
    BankSerializer,
    CloseLaySerializer,
    CuttingSettingsSerializer,
    GarmentModelSerializer,
    LayLineSerializer,
    LayListSerializer,
    LaySerializer,
    RecordOutputSerializer,
    RemnantLogSerializer,
    SavedFilterSerializer,
    SizeSetSerializer,
    TeamLeaderSerializer,
)


class ServiceErrorMixin:
    """Translate service and model failures into the shared error shape."""

    def handle_exception(self, exc):
        if isinstance(exc, services.LayValidationError):
            return Response(
                exceptions.issues_payload(exc.issues, "الفرشة مش جاهزة للعملية دي"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, DjangoValidationError):
            return Response(
                {
                    "detail": "البيانات مش مظبوطة",
                    "issues": exceptions.django_errors_to_issues(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, ValueError):
            return Response(
                {
                    "detail": str(exc),
                    "issues": [{
                        "code": "invalid", "level": "error",
                        "message": str(exc), "field": None, "line_no": None,
                    }],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)


# --- catalogues ----------------------------------------------------------

class BankViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    queryset = Bank.objects.all()
    serializer_class = BankSerializer
    permission_classes = [CanManageCatalogue]
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name"]


class SizeSetViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    queryset = SizeSet.objects.all()
    serializer_class = SizeSetSerializer
    permission_classes = [CanManageCatalogue]
    filterset_fields = ["is_active", "total_pieces"]
    search_fields = ["name", "sizes_raw"]

    @action(detail=False, methods=["post"], permission_classes=[CanViewCutting])
    def parse(self, request):
        """Split size text into rows and count the pieces, without saving.

        The new-lay screen calls this as the supervisor types.
        """
        raw = request.data.get("sizes_raw", "")
        try:
            pairs = size_utils.parse_sizes(raw)
        except size_utils.SizeParseError as exc:
            return Response(
                {
                    "detail": "المقاسات مش مقروءة",
                    "issues": [{
                        "code": "sizes_unreadable", "level": "error",
                        "message": str(exc), "field": "sizes_raw", "line_no": None,
                    }],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            "sizes_raw": size_utils.format_sizes(pairs),
            "sizes": [{"size": s, "pieces_in_ply": n} for s, n in pairs],
            "total_pieces": sum(n for _s, n in pairs),
        })


class GarmentModelViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    """The supervisor may add a model from the new-lay screen (SRS 7.2) but
    only the admin may change or remove one."""

    queryset = GarmentModel.objects.select_related("default_size_set")
    serializer_class = GarmentModelSerializer
    permission_classes = [CanAddToCatalogue]
    filterset_fields = ["category", "fit", "is_active"]
    search_fields = ["code", "name", "fit"]
    ordering_fields = ["code", "name", "created_at"]


class CuttingSettingsViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    queryset = CuttingSettings.objects.all()
    serializer_class = CuttingSettingsSerializer
    permission_classes = [CanManageCatalogue]

    def get_object(self):
        return CuttingSettings.get_solo()


# --- lays ----------------------------------------------------------------

class LayViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    permission_classes = [CanEditLays]
    filterset_class = filters.LayFilter
    search_fields = [
        "garment_model__code", "garment_model__name", "garment_model__fit",
        "team_leader__full_name", "notes",
        "lines__article", "lines__shade_note", "lines__lot_no", "lines__roll_no",
    ]
    # SRS 7.1: sortable by any column shown in the list.
    ordering_fields = [
        "start_date", "end_date", "lay_length_m", "lay_width_cm", "pieces_per_ply",
        "total_plies", "theoretical_pieces", "total_roll_length_m", "total_remnant_m",
        "consumed_m", "fabric_shortage_m", "expected_metrage", "real_metrage",
        "deviation_pct", "status", "created_at",
    ]
    ordering = ["-start_date", "-id"]

    def get_queryset(self):
        qs = (
            Lay.objects.select_related(
                "bank", "garment_model", "team_leader", "size_set", "entered_by"
            )
            .prefetch_related("size_breakdown", "output")
        )
        if self.action in ("retrieve", "update", "partial_update"):
            qs = qs.prefetch_related(
                Prefetch("lines", queryset=LayLine.objects.order_by("line_no")),
                "audit_entries",
                "team_members",
            )
        return filters.annotate_lay_queryset(qs)

    def get_serializer_class(self):
        return LayListSerializer if self.action == "list" else LaySerializer

    def perform_create(self, serializer):
        serializer.save(entered_by=self.request.user)

    # --- transitions ----------------------------------------------------

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Run every closing check, freeze the numbers, mark the lay closed.

        Errors block. Warnings block only until a reason is given, and the
        reason lands in the activity log.
        """
        lay = self.get_object()
        body = CloseLaySerializer(data=request.data)
        body.is_valid(raise_exception=True)

        result = services.close_lay(lay, request.user, body.validated_data["reason"])
        lay.refresh_from_db()
        return Response({
            "lay": LaySerializer(lay, context=self.get_serializer_context()).data,
            "issues": [exceptions.issue_dict(i) for i in result["issues"]],
        })

    @action(detail=True, methods=["get"])
    def validate(self, request, pk=None):
        """What closing would say, without closing. For the live UI."""
        lay = self.get_object()
        issues = validators.validate_for_close(lay)
        return Response({
            "can_close": not validators.has_errors(issues),
            "needs_reason": any(i.level == validators.WARNING for i in issues),
            "issues": [exceptions.issue_dict(i) for i in issues],
        })

    @action(detail=True, methods=["post"])
    def output(self, request, pk=None):
        """Record the counted pieces and split them across the sizes."""
        lay = self.get_object()
        body = RecordOutputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        services.record_output(
            lay,
            request.user,
            actual_pieces=data["actual_pieces"],
            rejected_pieces=data["rejected_pieces"],
            notes=data["notes"],
            manual=data.get("manual_distribution") or None,
        )
        lay.refresh_from_db()
        return Response(LaySerializer(lay, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        lay = self.get_object()
        if lay.status != Lay.STATUS_COUNTED:
            return Response(
                {
                    "detail": "الفرشة لازم تترقّم قبل الاعتماد",
                    "issues": [{
                        "code": "status", "level": "error",
                        "message": "الفرشة لازم تترقّم قبل الاعتماد",
                        "field": "status", "line_no": None,
                    }],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        Lay.objects.filter(pk=lay.pk).update(status=Lay.STATUS_APPROVED)
        lay.refresh_from_db()
        return Response(LaySerializer(lay, context=self.get_serializer_context()).data)

    # --- list-level reads -----------------------------------------------

    @action(detail=False, methods=["get"])
    def search(self, request):
        """One search box: free words plus shorthand tokens (SRS 7.1.1).

        `?q=ميتراج>1.2 عجز:نعم كارل` becomes the ordinary filter parameters
        plus a text search, so this endpoint and the plain list filter through
        exactly the same code.
        """
        free_text, params = search.parse_query(request.query_params.get("q", ""))

        merged = request.query_params.copy()
        merged.pop("q", None)
        for key, value in params.items():
            merged[key] = value
        if free_text:
            merged["search"] = free_text

        request._request.GET = merged
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        data = LayListSerializer(page, many=True, context=self.get_serializer_context()).data
        response = self.get_paginated_response(data)
        response.data["parsed"] = {
            "free_text": free_text,
            "filters": search.describe(params),
        }
        return response

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """The cards above the list, over whatever filters are applied."""
        qs = self.filter_queryset(self.get_queryset())
        agg = qs.aggregate(
            lays=Count("id", distinct=True),
            theoretical=Sum("theoretical_pieces"),
            actual=Sum("output__actual_pieces"),
            avg_real_metrage=Avg("real_metrage"),
            fabric=Sum("total_roll_length_m"),
        )
        return Response({
            "lays": agg["lays"] or 0,
            "theoretical_pieces": agg["theoretical"] or 0,
            "actual_pieces": agg["actual"] or 0,
            "avg_real_metrage": agg["avg_real_metrage"],
            "total_fabric_m": agg["fabric"] or 0,
            "with_shortage": qs.filter(has_shortage=True).count(),
            "awaiting_count": qs.filter(
                status=Lay.STATUS_CLOSED, output__isnull=True
            ).count(),
        })

    # --- reads ----------------------------------------------------------

    @action(detail=True, methods=["get"])
    def calculations(self, request, pk=None):
        lay = self.get_object()
        values = services.calculate(lay)
        return Response({
            **{k: v for k, v in values.items()},
            **services.pieces_loss(lay),
            "working_days": lay.working_days,
            "productivity": services.team_leader_productivity(lay),
        })

    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        lay = self.get_object()
        last = lay.lines.order_by("-line_no").values_list("line_no", flat=True).first()
        payload = {**request.data, "lay": lay.pk}
        payload.setdefault("line_no", (last or 0) + 1)
        serializer = LayLineSerializer(
            data=payload, context={**self.get_serializer_context(), "lay": lay}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        services.recalculate(lay)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def attachments(self, request, pk=None):
        """Upload the notebook page. Required before closing (SRS 4.6)."""
        lay = self.get_object()
        image = request.FILES.get("sheet_image")
        if image is None:
            return Response(
                {
                    "detail": "مفيش صورة مرفوعة",
                    "issues": [{
                        "code": "V10", "level": "error",
                        "message": "مفيش صورة مرفوعة", "field": "sheet_image", "line_no": None,
                    }],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        lay.sheet_image = image
        lay.save(update_fields=["sheet_image"])
        return Response(LaySerializer(lay, context=self.get_serializer_context()).data)


class SavedFilterViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    """Named searches. Everyone sees their own plus anything marked shared."""

    serializer_class = SavedFilterSerializer
    permission_classes = [CanViewCutting]

    def get_queryset(self):
        return SavedFilter.objects.filter(
            models.Q(owner=self.request.user) | models.Q(is_shared=True)
        ).select_related("owner")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        # A shared filter belongs to whoever made it.
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied("البحث ده مش بتاعك")
        instance.delete()


class LayLineViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    queryset = LayLine.objects.select_related("lay")
    serializer_class = LayLineSerializer
    permission_classes = [CanEditLays]
    filterset_fields = ["lay", "article", "lot_no", "roll_end_action", "remnant_disposition"]

    def perform_create(self, serializer):
        line = serializer.save()
        services.recalculate(line.lay)

    def perform_update(self, serializer):
        line = serializer.save()
        services.recalculate(line.lay)

    def perform_destroy(self, instance):
        lay = instance.lay
        instance.delete()
        services.recalculate(lay)


class RemnantLogViewSet(ServiceErrorMixin, viewsets.ReadOnlyModelViewSet):
    """View only — no balance and no "use it" button until inventory (SRS 7.6)."""

    queryset = RemnantLog.objects.select_related("lay_line", "lay_line__lay")
    serializer_class = RemnantLogSerializer
    permission_classes = [CanViewCutting]
    filterset_class = filters.RemnantLogFilter
    search_fields = ["article", "lot_no", "shade_note"]
    ordering_fields = ["logged_at", "length_m"]


@api_view(["GET"])
@permission_classes([CanViewCutting])
def team_leaders(request):
    """Team leaders, the ones the device saw inside the lay's dates first.

    `?date=` for a one-day lay, `?date_from=&date_to=` for a spread. Entry
    happens days after the fact, so the lay's own dates are what matter, never
    today's (SRS section 6).
    """
    def _parse(name):
        raw = request.query_params.get(name)
        if not raw:
            return None
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            return None

    single = _parse("date")
    start = _parse("date_from") or single
    end = _parse("date_to") or single or start

    employees = list(Employee.objects.filter(is_active=True, is_team_leader=True))
    if not employees:  # nobody flagged yet — fall back to all active staff
        employees = list(Employee.objects.filter(is_active=True))

    codes = present_codes(start, end) if start else set()
    for emp in employees:
        emp.was_present = emp.employee_code in codes

    employees.sort(key=lambda e: (not e.was_present, e.full_name))
    return Response(TeamLeaderSerializer(employees, many=True).data)
