from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.tenants.urls")),
    path("api/", include("apps.collection.urls")),
    path("api/", include("apps.farmers.urls")),
    path("api/", include("apps.milk.urls")),
    path("api/", include("apps.store.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/", include("apps.payroll.urls")),
    path("api/", include("apps.expenses.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.mpesa.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.advances.urls")),
    path("api/", include("apps.herd.urls")),
    path("api/", include("apps.sales.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.platform_admin.urls")),
    path("api/", include("apps.dashboard.urls")),
]
