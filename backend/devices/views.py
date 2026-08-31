import datetime

from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from hr.permissions import IsAdmin, IsAdminOrHR
from . import services
from .models import AttendanceLog, Device, DeviceCommand


class DeviceSerializer(serializers.ModelSerializer):
    online = serializers.SerializerMethodField()
    pending_commands = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            "id", "serial_number", "name", "last_seen", "push_version",
            "is_active", "online", "pending_commands",
        ]

    def get_online(self, obj):
        return bool(
            obj.last_seen
            and obj.last_seen >= timezone.now() - datetime.timedelta(minutes=2)
        )

    def get_pending_commands(self, obj):
        return obj.commands.filter(status__in=["pending", "sent"]).count()


class DeviceCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceCommand
        fields = [
            "id", "device", "command", "description", "status",
            "return_code", "created_at", "sent_at", "finished_at",
        ]


class AttendanceLogSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    local_time = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceLog
        fields = [
            "id", "employee_code", "employee", "employee_name",
            "timestamp", "local_time", "punch_state", "verify_type", "source",
        ]
        read_only_fields = ["employee_code", "source"]

    def get_employee_name(self, obj):
        return obj.employee.full_name if obj.employee else ""

    def get_local_time(self, obj):
        return timezone.localtime(obj.timestamp).isoformat()


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.order_by("id")
    serializer_class = DeviceSerializer
    permission_classes = [IsAdmin]
    pagination_class = None
    http_method_names = ["get", "patch", "post", "head", "options"]

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        cmd = services.check_data(self.get_object())
        return Response({"command_id": cmd.id}, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def reboot(self, request, pk=None):
        cmd = services.reboot(self.get_object())
        return Response({"command_id": cmd.id}, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def wipe(self, request, pk=None):
        """Full reset: erase the server database AND the device's stored
        users/fingerprints/logs, then start clean. Irreversible."""
        from django.utils import timezone as tz
        from hr.models import Employee
        from .models import AttendanceLog, DeviceCommand, FingerprintTemplate

        device = self.get_object()
        # Guard first so pushes arriving mid-wipe are dropped, not re-stored.
        device.wipe_requested_at = tz.now()
        device.save(update_fields=["wipe_requested_at"])

        removed = {
            "attendance": AttendanceLog.objects.count(),
            "fingerprints": FingerprintTemplate.objects.count(),
            "employees": Employee.objects.count(),
        }
        AttendanceLog.objects.all().delete()
        FingerprintTemplate.objects.all().delete()
        Employee.objects.all().delete()
        # Drop any queued commands so CLEAR DATA is the only thing the device
        # sees next — a stale REBOOT/CHECK must not jump ahead of the wipe.
        DeviceCommand.objects.filter(device=device).delete()

        cmd = services.clear_all_data(device)
        return Response({"command_id": cmd.id, "removed": removed}, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin], url_path="clear-logs")
    def clear_logs(self, request, pk=None):
        cmd = services.clear_attendance(self.get_object())
        return Response({"command_id": cmd.id}, status=201)

    @action(detail=True, methods=["get"])
    def commands(self, request, pk=None):
        qs = self.get_object().commands.order_by("-created_at")[:50]
        return Response(DeviceCommandSerializer(qs, many=True).data)


class DeviceCommandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceCommand.objects.order_by("-created_at")
    serializer_class = DeviceCommandSerializer
    permission_classes = [IsAdmin]


class AttendanceLogViewSet(viewsets.ModelViewSet):
    queryset = AttendanceLog.objects.select_related("employee").order_by("-timestamp")
    serializer_class = AttendanceLogSerializer
    permission_classes = [IsAdminOrHR]
    filterset_fields = ["employee_code", "device"]
    search_fields = ["employee_code", "employee__full_name"]

    def create(self, request, *args, **kwargs):
        # Raw punches aren't created directly — use the `manual` action, which
        # applies the check-in/check-out shortcuts consistently.
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed("POST")

    def get_queryset(self):
        qs = super().get_queryset()
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        return qs

    @action(detail=False, methods=["get"])
    def day(self, request):
        """All punches for one employee on one day, earliest first."""
        from hr.models import Employee

        emp = Employee.objects.filter(id=request.query_params.get("employee")).first()
        day = request.query_params.get("date")
        if not emp or not day:
            return Response({"detail": "employee و date مطلوبان"}, status=400)
        logs = (
            AttendanceLog.objects.filter(employee_code=emp.employee_code, timestamp__date=day)
            .order_by("timestamp")
        )
        return Response(
            {
                "employee": {"id": emp.id, "full_name": emp.full_name, "employee_code": emp.employee_code},
                "date": day,
                "punches": AttendanceLogSerializer(logs, many=True).data,
            }
        )

    @action(detail=False, methods=["post"])
    def manual(self, request):
        """Upsert a manual check-in and/or check-out for an employee on a day.

        Body: {employee, date, check_in: "08:00"|null, check_out: "17:00"|null}
        A null/empty time removes any existing *manual* punch of that kind;
        device punches are never touched here.
        """
        from hr.models import Employee

        emp = Employee.objects.filter(id=request.data.get("employee")).first()
        if not emp:
            return Response({"detail": "الموظف غير موجود"}, status=400)
        try:
            day = datetime.date.fromisoformat(request.data.get("date", ""))
        except ValueError:
            return Response({"detail": "التاريخ غير صحيح"}, status=400)

        tz = timezone.get_current_timezone()
        # (field name, punch_state): 0 = check-in, 1 = check-out
        for field, state in (("check_in", 0), ("check_out", 1)):
            raw = request.data.get(field)
            existing = AttendanceLog.objects.filter(
                employee_code=emp.employee_code,
                timestamp__date=day,
                punch_state=state,
                source="manual",
            )
            if not raw:
                existing.delete()
                continue
            try:
                t = datetime.time.fromisoformat(raw)
            except ValueError:
                return Response({"detail": f"وقت غير صحيح: {raw}"}, status=400)
            ts = timezone.make_aware(datetime.datetime.combine(day, t), tz)
            row = existing.first()
            if row:
                row.timestamp = ts
                row.employee = emp
                row.save(update_fields=["timestamp", "employee"])
            else:
                AttendanceLog.objects.create(
                    employee=emp,
                    employee_code=emp.employee_code,
                    timestamp=ts,
                    punch_state=state,
                    verify_type=100,
                    source="manual",
                    device=None,
                )
        logs = AttendanceLog.objects.filter(
            employee_code=emp.employee_code, timestamp__date=day
        ).order_by("timestamp")
        return Response(
            {"punches": AttendanceLogSerializer(logs, many=True).data}, status=200
        )
