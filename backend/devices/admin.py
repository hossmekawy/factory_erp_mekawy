from django.contrib import admin

from .models import AttendanceLog, Device, DeviceCommand, FingerprintTemplate


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["serial_number", "name", "last_seen", "is_active"]


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ["employee_code", "employee", "timestamp", "punch_state", "verify_type"]
    search_fields = ["employee_code"]
    list_filter = ["device"]
    date_hierarchy = "timestamp"


@admin.register(FingerprintTemplate)
class FingerprintTemplateAdmin(admin.ModelAdmin):
    list_display = ["employee_code", "finger_id", "valid", "updated_at"]
    search_fields = ["employee_code"]


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
    list_display = ["id", "device", "description", "status", "created_at", "finished_at"]
    list_filter = ["status", "device"]
