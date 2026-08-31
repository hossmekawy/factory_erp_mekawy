from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from devices import iclock_views
from devices.views import AttendanceLogViewSet, DeviceCommandViewSet, DeviceViewSet
from hr import views as hr_views

router = DefaultRouter()
router.register("departments", hr_views.DepartmentViewSet)
router.register("employees", hr_views.EmployeeViewSet)
router.register("users", hr_views.SystemUserViewSet)
router.register("devices", DeviceViewSet)
router.register("commands", DeviceCommandViewSet)
router.register("attendance", AttendanceLogViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    # ZKTeco ADMS push protocol (device-facing, plain text)
    path("iclock/cdata", iclock_views.cdata),
    path("iclock/getrequest", iclock_views.getrequest),
    path("iclock/devicecmd", iclock_views.devicecmd),
    path("iclock/ping", iclock_views.ping),
    # REST API (browser-facing, JWT)
    path("api/auth/login/", TokenObtainPairView.as_view()),
    path("api/auth/refresh/", TokenRefreshView.as_view()),
    path("api/dashboard/", hr_views.dashboard),
    path("api/me/", hr_views.me),
    path("api/schedule/", hr_views.work_schedule),
    path("api/settings/", hr_views.settings_view),
    path("api/settings/public/", hr_views.settings_public),
    path("api/settings/favicon/", hr_views.settings_favicon),
    path("api/reports/weekly/", hr_views.weekly_report),
    path("api/reports/weekly/export/", hr_views.weekly_report_export),
    path("api/reports/weekly/pdf/", hr_views.weekly_report_pdf),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
