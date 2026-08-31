import datetime

from django.contrib.auth.models import User
from django.db.models import Count
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from devices import services as device_services
from devices.models import AttendanceLog, Device, FingerprintTemplate
from .icons import generate_site_icons
from .models import Department, Employee, SiteSettings, WorkSchedule
from .permissions import IsAdmin, IsAdminOrHR, role_of
from .reports import build_weekly_report, week_start_for, weekly_report_xlsx
from .reports_pdf import build_weekly_pdf
from .serializers import (
    DepartmentSerializer,
    EmployeeSerializer,
    FingerprintSerializer,
    SystemUserSerializer,
    WorkScheduleSerializer,
)


def _role_of(user) -> str:
    return role_of(user)


def _icon_urls(site: SiteSettings) -> dict:
    # Relative paths on purpose: this data is fetched both by the browser
    # (through nginx on the public domain) and by Next.js server-side code
    # calling the backend directly over 127.0.0.1 — an absolute URL built
    # from that internal request would be unreachable from the browser.
    # nginx serves /media/ on the public domain too, so a relative path
    # resolves correctly either way.
    def url(field):
        f = getattr(site, field)
        return f.url if f else None

    return {
        "favicon_url": url("favicon"),
        "icon_192_url": url("icon_192"),
        "icon_512_url": url("icon_512"),
        "apple_touch_icon_url": url("apple_touch_icon"),
    }


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.annotate(employee_count=Count("employee")).order_by("name")
    serializer_class = DepartmentSerializer
    permission_classes = [IsAdminOrHR]
    pagination_class = None


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related("department").all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAdminOrHR]
    filterset_fields = ["department", "is_active"]
    search_fields = ["full_name", "employee_code", "national_id", "phone_number"]

    def perform_create(self, serializer):
        employee = serializer.save()
        for device in Device.objects.filter(is_active=True):
            device_services.update_user(device, employee)

    def perform_destroy(self, instance):
        for device in Device.objects.filter(is_active=True):
            device_services.delete_user(device, instance.employee_code)
        instance.delete()

    @action(detail=True, methods=["get"])
    def fingerprints(self, request, pk=None):
        emp = self.get_object()
        fps = FingerprintTemplate.objects.filter(employee_code=emp.employee_code)
        return Response(FingerprintSerializer(fps, many=True).data)

    @action(detail=True, methods=["post"], url_path="enroll-fp")
    def enroll_fp(self, request, pk=None):
        emp = self.get_object()
        try:
            finger_id = int(request.data.get("finger_id", 6))
        except (TypeError, ValueError):
            return Response({"detail": "finger_id غير صحيح"}, status=400)
        if not 0 <= finger_id <= 9:
            return Response({"detail": "رقم الإصبع يجب أن يكون من 0 إلى 9"}, status=400)
        device_id = request.data.get("device")
        devices = Device.objects.filter(is_active=True)
        if device_id:
            devices = devices.filter(id=device_id)
        device = devices.first()
        if device is None:
            return Response({"detail": "لا يوجد جهاز بصمة متصل"}, status=400)
        # The person must exist on the device before ENROLL_FP will work.
        device_services.update_user(device, emp)
        cmd = device_services.enroll_fingerprint(device, emp.employee_code, finger_id)
        return Response({"command_id": cmd.id, "status": cmd.status}, status=201)

    @action(detail=True, methods=["post"], url_path="push-to-device")
    def push_to_device(self, request, pk=None):
        emp = self.get_object()
        cmds = []
        for device in Device.objects.filter(is_active=True):
            cmds.append(device_services.update_user(device, emp).id)
            for fp in FingerprintTemplate.objects.filter(
                employee_code=emp.employee_code, valid=1
            ):
                cmds.append(device_services.push_fingerprint(device, fp).id)
        if not cmds:
            return Response({"detail": "لا يوجد جهاز بصمة متصل"}, status=400)
        return Response({"command_ids": cmds}, status=201)

    @action(detail=True, methods=["get"])
    def attendance(self, request, pk=None):
        emp = self.get_object()
        qs = AttendanceLog.objects.filter(employee_code=emp.employee_code)
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        page = self.paginate_queryset(qs)
        data = [
            {
                "id": log.id,
                "timestamp": timezone.localtime(log.timestamp).isoformat(),
                "punch_state": log.punch_state,
                "verify_type": log.verify_type,
            }
            for log in page
        ]
        return self.get_paginated_response(data)


class SystemUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = SystemUserSerializer
    permission_classes = [IsAdmin]
    pagination_class = None

    def get_queryset(self):
        return User.objects.order_by("username")

    def perform_destroy(self, instance):
        if instance == self.request.user:
            return
        instance.is_active = False
        instance.save(update_fields=["is_active"])


@api_view(["GET", "PUT"])
@permission_classes([IsAdminOrHR])
def work_schedule(request):
    schedule = WorkSchedule.get_solo()
    if request.method == "PUT":
        if not IsAdmin().has_permission(request, None):
            return Response(status=status.HTTP_403_FORBIDDEN)
        ser = WorkScheduleSerializer(schedule, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
    return Response(WorkScheduleSerializer(schedule).data)


def _parse_week(request):
    raw = request.query_params.get("week")
    if raw:
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


@api_view(["GET"])
@permission_classes([IsAdminOrHR])
def weekly_report(request):
    return Response(build_weekly_report(_parse_week(request)))


@api_view(["GET"])
@permission_classes([IsAdminOrHR])
def weekly_report_export(request):
    anchor = _parse_week(request)
    report = build_weekly_report(anchor)
    buf = weekly_report_xlsx(report)
    filename = f"weekly-report-{week_start_for(anchor).isoformat()}.xlsx"
    return FileResponse(
        buf,
        as_attachment=True,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@api_view(["GET"])
@permission_classes([IsAdminOrHR])
def weekly_report_pdf(request):
    anchor = _parse_week(request)
    size = "a5" if request.query_params.get("size", "a4").lower() == "a5" else "a4"
    report = build_weekly_report(anchor)
    buf = build_weekly_pdf(report, size)
    filename = f"weekly-report-{week_start_for(anchor).isoformat()}-{size}.pdf"
    return FileResponse(
        buf, as_attachment=True, filename=filename, content_type="application/pdf"
    )


@api_view(["GET"])
@permission_classes([IsAdmin])
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()
    online_cutoff = now - datetime.timedelta(minutes=2)
    devices = [
        {
            "id": d.id,
            "serial_number": d.serial_number,
            "name": d.name,
            "last_seen": timezone.localtime(d.last_seen).isoformat() if d.last_seen else None,
            "online": bool(d.last_seen and d.last_seen >= online_cutoff),
        }
        for d in Device.objects.filter(is_active=True)
    ]
    present_today = (
        AttendanceLog.objects.filter(timestamp__date=today)
        .values("employee_code")
        .distinct()
        .count()
    )
    latest = [
        {
            "id": log.id,
            "employee_code": log.employee_code,
            "employee_name": log.employee.full_name if log.employee else log.employee_code,
            "timestamp": timezone.localtime(log.timestamp).isoformat(),
        }
        for log in AttendanceLog.objects.select_related("employee").order_by("-timestamp")[:10]
    ]
    me = request.user
    return Response(
        {
            "devices": devices,
            "employees_active": Employee.objects.filter(is_active=True).count(),
            "present_today": present_today,
            "latest_punches": latest,
            "me": {"username": me.username, "role": _role_of(me)},
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Lightweight identity endpoint every logged-in role can call — used by
    the app shell for the sidebar, independent of the (admin-only) dashboard."""
    u = request.user
    return Response({"username": u.username, "role": _role_of(u)})


@api_view(["GET", "PUT"])
@permission_classes([IsAdmin])
def settings_view(request):
    schedule = WorkSchedule.get_solo()
    site = SiteSettings.get_solo()
    if request.method == "PUT":
        data = request.data
        if "company_name" in data:
            site.company_name = data["company_name"] or site.company_name
            site.save(update_fields=["company_name"])
        sched_ser = WorkScheduleSerializer(schedule, data=data, partial=True)
        sched_ser.is_valid(raise_exception=True)
        sched_ser.save()

    payload = WorkScheduleSerializer(schedule).data
    payload["company_name"] = site.company_name
    payload.update(_icon_urls(site))
    payload["updated_at"] = site.updated_at.isoformat()
    return Response(payload)


@api_view(["GET"])
@permission_classes([AllowAny])
def settings_public(request):
    """Branding only — no schedule/business data. Used by the frontend layout
    and PWA manifest, which render before any user is authenticated."""
    site = SiteSettings.get_solo()
    payload = {"company_name": site.company_name, "updated_at": site.updated_at.isoformat()}
    payload.update(_icon_urls(site))
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAdmin])
def settings_favicon(request):
    upload = request.FILES.get("image")
    if not upload:
        return Response({"detail": "أرفق صورة"}, status=400)
    if upload.size > 8 * 1024 * 1024:
        return Response({"detail": "الصورة كبيرة جداً (الحد الأقصى 8 ميجا)"}, status=400)
    site = SiteSettings.get_solo()
    try:
        generate_site_icons(site, upload)
    except Exception:
        return Response({"detail": "تعذر قراءة الصورة — جرّب صيغة PNG أو JPG"}, status=400)
    payload = _icon_urls(site)
    payload["updated_at"] = site.updated_at.isoformat()
    return Response(payload, status=201)
