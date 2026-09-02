"""ViewSets for the cutting module.

Thin by design: they authorise, shape the queryset, and hand off. Every
calculation is in `services` and every rule is in the models or `validators`,
so nothing here can drift from what the admin and the shell enforce.

Failures come back in one shape, carrying the SRS rule number — see
`exceptions.issues_payload`.
"""
import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.db import models, transaction
from django.db.models import Avg, Count, Prefetch, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from hr.attendance import present_codes
from hr.models import Employee

from . import exceptions, filters, notifications, search, services
from . import lay_pdf
from . import reports as cutting_reports
from . import sizes as size_utils
from . import validators
from .models import (
    Bank,
    CuttingSettings,
    Category,
    GarmentModel,
    Lay,
    LayAudit,
    LayLine,
    Notification,
    RemnantLog,
    SavedFilter,
    SizeSet,
)
from .permissions import (
    _role,
    CanAddToCatalogue,
    CanEditLays,
    CanManageCatalogue,
    CanViewCutting,
)
from .serializers import (
    BankSerializer,
    CloseLaySerializer,
    CuttingSettingsSerializer,
    CategorySerializer,
    GarmentModelSerializer,
    LayLineSerializer,
    LayListSerializer,
    LaySerializer,
    RecordOutputSerializer,
    NotificationSerializer,
    RemnantLogSerializer,
    SavedFilterSerializer,
    SizeSetSerializer,
    TeamLeaderSerializer,
)


class ServiceErrorMixin:
    """Translate service and model failures into the shared error shape."""

    def handle_exception(self, exc):
        if isinstance(exc, ProtectedError):
            # A catalogue row a lay still points at. The database is right to
            # refuse; the client deserves to be told why rather than given a 500.
            return Response(
                {
                    "detail": "مينفعش يتمسح — فيه فرشات مرتبطة بيه",
                    "issues": [{
                        "code": "in_use", "level": "error",
                        "message": "مينفعش يتمسح — فيه فرشات أو موديلات مرتبطة بيه",
                        "field": None, "line_no": None,
                    }],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
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
    """Size sets. `?is_preset=true` is the list worth offering anyone — the
    rest are snapshots left behind by lays whose sizes were typed by hand."""

    queryset = SizeSet.objects.select_related("category")
    serializer_class = SizeSetSerializer
    permission_classes = [CanAddToCatalogue]
    filterset_fields = ["is_active", "total_pieces", "is_preset", "category"]
    search_fields = ["name", "sizes_raw"]
    ordering_fields = ["name", "total_pieces", "created_at"]
    ordering = ["name"]

    def perform_create(self, serializer):
        # Anything created through this endpoint was created on purpose.
        serializer.save(is_preset=True)

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


class CategoryViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    """The sections the factory sorts its models into. Renaming one here
    renames it on every model that carries it."""

    serializer_class = CategorySerializer
    permission_classes = [CanAddToCatalogue]
    filterset_fields = ["is_active"]
    search_fields = ["name", "notes"]
    ordering_fields = ["name", "order", "created_at"]
    # Annotating drops the model's Meta ordering, and an unordered queryset
    # paginates inconsistently.
    ordering = ["order", "name"]

    def get_queryset(self):
        return Category.objects.annotate(model_count=Count("models", distinct=True))


class GarmentModelViewSet(ServiceErrorMixin, viewsets.ModelViewSet):
    """The supervisor may add and correct a model; only the admin deletes one."""

    serializer_class = GarmentModelSerializer
    permission_classes = [CanAddToCatalogue]

    def get_queryset(self):
        return GarmentModel.objects.select_related(
            "default_size_set", "category"
        ).annotate(lay_count=Count("lays", distinct=True))
    filterset_fields = ["category", "is_active"]
    search_fields = ["name", "code"]   # name first: models are found by name
    ordering_fields = ["code", "name", "created_at"]
    ordering = ["name"]


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
        "code", "garment_model__name", "garment_model__code",
        "team_leader__full_name", "notes",
        "lines__shade_note",
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
            .prefetch_related("size_breakdown", "shade_breakdown", "output")
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

    def perform_destroy(self, instance):
        """An open lay is a draft and whoever may write may bin it. A closed one
        has frozen numbers, an activity log and possibly a count hanging off it,
        so removing it is the admin's call."""
        if instance.status != Lay.STATUS_OPEN and _role(self.request) != "admin":
            raise PermissionDenied("القصة مقفولة — الحذف للأدمن بس")
        instance.delete()

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
        data = body.validated_data

        # Closing and counting go in one transaction when the count came with
        # the request: a failure in the second half must not leave a lay
        # closed with a count that never landed.
        with transaction.atomic():
            result = services.close_lay(lay, request.user, data["reason"])
            if data.get("actual_pieces") is not None:
                services.record_output(
                    lay,
                    request.user,
                    actual_pieces=data["actual_pieces"],
                    rejected_pieces=data["rejected_pieces"],
                    notes=data["output_notes"],
                )
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

    @action(detail=True, methods=["get"])
    def distribution(self, request, pk=None):
        """Preview how a count would split across the sizes, without saving.

        The counting screen shows the split before the supervisor commits, and
        it asks the server for it rather than repeating the largest-remainder
        rule in TypeScript — the parts have to add to the total exactly, and
        one implementation of that is enough.
        """
        lay = self.get_object()
        raw = request.query_params.get("actual_pieces", "")
        try:
            actual = int(raw)
        except (TypeError, ValueError):
            return Response(
                {
                    "detail": "لازم تبعت عدد القطع",
                    "issues": [{
                        "code": "invalid", "level": "error",
                        "message": "لازم تبعت عدد القطع",
                        "field": "actual_pieces", "line_no": None,
                    }],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = list(lay.size_breakdown.all())
        split = size_utils.distribute(actual, [(b.size, b.pieces_in_ply) for b in rows])
        issues = validators.validate_output(lay, actual)
        return Response({
            "actual_pieces": actual,
            "theoretical_pieces": lay.theoretical_pieces,
            "sizes": [
                {
                    "size": b.size,
                    "pieces_in_ply": b.pieces_in_ply,
                    "theoretical_pieces": b.theoretical_pieces,
                    "actual_pieces": split[b.size],
                }
                for b in rows
            ],
            **services.pieces_loss_for(lay, actual),
            "issues": [exceptions.issue_dict(i) for i in issues],
        })

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """A printable sheet for one lay: `?paper=a4` (default) or `?paper=a5`.

        Not the browser's own print — that put the navigation and the buttons
        on the paper. This is a real document with the factory's name and logo,
        in grey-scale because these come off an office laser printer.

        The parameter is `paper`, not `size`: `size` is already the filter for
        "a garment size present in this lay", and get_object() runs the
        filters, so `?size=a5` filtered the lay away and answered 404.
        """
        lay = self.get_object()
        buf = lay_pdf.build_lay_pdf(lay, request.query_params.get("paper", "a4"))
        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="lay-{lay.code}.pdf"'
        return response

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
    def export(self, request):
        """Excel or PDF of the list, under whatever filters are applied —
        the same queryset the screen is showing (SRS 7.1)."""
        qs = self.filter_queryset(self.get_queryset())
        rows = [
            {
                "code": lay.code,
                "date": (
                    f"{lay.start_date} → {lay.end_date}"
                    if lay.is_multi_day else str(lay.start_date)
                ),
                "model": lay.garment_model.name,
                "sizes": " ".join(b.size for b in lay.size_breakdown.all()),
                "lay_length_m": lay.lay_length_m,
                "pieces_per_ply": lay.pieces_per_ply,
                "total_plies": lay.total_plies,
                "theoretical_pieces": lay.theoretical_pieces,
                "actual_pieces": getattr(getattr(lay, "output", None), "actual_pieces", None),
                "expected_metrage": lay.expected_metrage,
                "real_metrage": lay.real_metrage,
                "deviation_pct": lay.deviation_pct,
                "shortage": lay.fabric_shortage_m,
                "team_leader": lay.team_leader.full_name,
                "bank": lay.bank.name,
                "status": lay.get_status_display(),
            }
            for lay in qs.prefetch_related("size_breakdown")
        ]
        report = {
            "title": "الفرشات",
            "period": {
                "start": request.query_params.get("date_from"),
                "end": request.query_params.get("date_to"),
            },
            "columns": [
                ("code", "كود القصة"), ("date", "التاريخ"), ("model", "الموديل"),
                ("sizes", "المقاسات"), ("lay_length_m", "طول الفرشة"),
                ("pieces_per_ply", "ق/راق"), ("total_plies", "إجمالي الراق"),
                ("theoretical_pieces", "القطع النظرية"), ("actual_pieces", "القطع الفعلية"),
                ("expected_metrage", "المتوقع"), ("real_metrage", "الحقيقي"),
                ("deviation_pct", "الانحراف %"), ("shortage", "العجز"),
                ("team_leader", "رئيس الفريق"), ("bank", "البنك"), ("status", "الحالة"),
            ],
            "rows": rows,
        }
        return _as_download(report, request.query_params.get("export", "xlsx"), "cutting-lays")

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
            "shades": services.shade_totals(lay),
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


class NotificationViewSet(ServiceErrorMixin, viewsets.ReadOnlyModelViewSet):
    """Each user sees only their own alerts (SRS 11.1)."""

    serializer_class = NotificationSerializer
    permission_classes = [CanViewCutting]
    filterset_fields = ["kind", "is_read"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related("lay", "lay__garment_model")

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({
            "unread": Notification.objects.filter(
                recipient=request.user, is_read=False
            ).count()
        })

    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        """Pass `ids` to mark some, or nothing at all to mark everything."""
        ids = request.data.get("ids")
        marked = notifications.mark_read(request.user, ids)
        return Response({"marked": marked})


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
    """Roll lines, editable in their own right.

    A line typed wrong used to mean deleting the whole lay and entering it
    again, which is not a thing anyone will do at a bank with a notebook in
    hand. The rules match the header's: an open lay changes freely, a closed
    one needs a reason and the reason is recorded.

    Every write recalculates the lay — plies, metrage, shortage and the shade
    split all move together — so the stored numbers can never drift from the
    lines they came from.
    """

    queryset = LayLine.objects.select_related("lay")
    serializer_class = LayLineSerializer
    permission_classes = [CanEditLays]
    filterset_fields = ["lay", "roll_end_action", "remnant_disposition"]

    def _reason(self):
        return (self.request.data.get("edit_reason") or "").strip()

    def _require_reason(self, lay):
        """SRS 3, applied to the lines as well as the header."""
        if lay.status == Lay.STATUS_OPEN:
            return
        if not self._reason():
            raise DRFValidationError({
                "detail": "القصة مقفولة — لازم سبب للتعديل",
                "issues": [{
                    "code": "edit_reason", "level": "error",
                    "message": "القصة مقفولة. اكتب سبب التعديل — بيتسجّل في سجل النشاط.",
                    "field": "edit_reason", "line_no": None,
                }],
            })

    def _log(self, lay, action, line, before=None):
        if lay.status == Lay.STATUS_OPEN:
            return
        LayAudit.objects.create(
            lay=lay, user=self.request.user, action=action,
            field=f"سطر {line.line_no}",
            old_value=before or "", new_value=_describe_line(line) if before is None else
            _describe_line(line),
            reason=self._reason(),
        )

    def perform_create(self, serializer):
        lay = serializer.validated_data.get("lay")
        self._require_reason(lay)
        line = serializer.save()
        services.recalculate(line.lay)
        self._log(line.lay, "line_added", line)

    def perform_update(self, serializer):
        before = _describe_line(serializer.instance)
        self._require_reason(serializer.instance.lay)
        line = serializer.save()
        services.recalculate(line.lay)
        self._log(line.lay, "line_edited", line, before=before)

    def perform_destroy(self, instance):
        lay = instance.lay
        self._require_reason(lay)
        described = _describe_line(instance)
        line_no = instance.line_no
        instance.delete()
        services.recalculate(lay)
        if lay.status != Lay.STATUS_OPEN:
            LayAudit.objects.create(
                lay=lay, user=self.request.user, action="line_deleted",
                field=f"سطر {line_no}", old_value=described, new_value="",
                reason=self._reason(),
            )


class RemnantLogViewSet(ServiceErrorMixin, viewsets.ReadOnlyModelViewSet):
    """View only — no balance and no "use it" button until inventory (SRS 7.6)."""

    queryset = RemnantLog.objects.select_related("lay_line", "lay_line__lay")
    serializer_class = RemnantLogSerializer
    permission_classes = [CanViewCutting]
    filterset_class = filters.RemnantLogFilter
    search_fields = ["article", "lot_no", "shade_note"]
    ordering_fields = ["logged_at", "length_m"]


def _describe_line(line) -> str:
    """One readable line for the activity log, so an edit can be read back."""
    parts = [f"{line.roll_length_m} م", f"{line.plies} راق"]
    if line.remnant_m:
        parts.append(f"باقي {line.remnant_m}")
    if line.shade_note:
        parts.append(line.shade_note)
    return " · ".join(parts)


def _parse_date(request, name):
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _as_download(report, fmt, stem):
    """json / xlsx / pdf from the same report dict (the hr/reports.py pattern).

    The query parameter is `export`, not `format`: DRF reserves `format` for
    picking a renderer and answers 404 for a value it has no renderer for,
    before the view ever runs.
    """
    if fmt == "xlsx":
        buf = cutting_reports.report_xlsx(report)
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{stem}.xlsx"'
        return response
    if fmt == "pdf":
        buf = cutting_reports.report_pdf(report)
        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
        return response
    return Response(report)


@api_view(["GET"])
@permission_classes([CanViewCutting])
def report_view(request, name):
    """/api/cutting/reports/{name}/?date_from=&date_to=&format=json|xlsx|pdf"""
    builder = cutting_reports.REPORTS.get(name)
    if builder is None:
        return Response(
            {"detail": "التقرير ده مش موجود",
             "available": sorted(cutting_reports.REPORTS)},
            status=status.HTTP_404_NOT_FOUND,
        )
    report = builder(
        start=_parse_date(request, "date_from"),
        end=_parse_date(request, "date_to"),
        include_backfill=request.query_params.get("include_backfill") == "true",
    )
    return _as_download(report, request.query_params.get("export", "json"), f"cutting-{name}")


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
