from django.contrib import admin

from .models import Department, Employee, WorkSchedule

admin.site.site_header = "MR.Mekawy Factory ERP"
admin.site.site_title = "MR.Mekawy Factory ERP"


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name"]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["employee_code", "full_name", "department", "job_title", "is_active"]
    search_fields = ["employee_code", "full_name", "national_id"]
    list_filter = ["department", "is_active"]


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ["work_start", "work_end", "weekend_days"]
