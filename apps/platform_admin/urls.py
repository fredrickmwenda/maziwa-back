from django.urls import path

from . import views

urlpatterns = [
    path("platform/orgs/", views.platform_orgs),
    path("platform/orgs/<int:pk>/suspend/", views.platform_suspend),
    path("platform/roles/", views.platform_roles),
    path("platform/audit/", views.platform_audit),
    path("platform/invoices/", views.platform_invoices),
    path("platform/invoices/<int:pk>/confirm/", views.platform_confirm),
]
