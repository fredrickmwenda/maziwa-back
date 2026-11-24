from django.urls import path

from . import views

urlpatterns = [
    path("export/<str:dataset>/", views.export_data),
    path("reports/statement/", views.farmer_statement),
    path("reports/statement/<int:farmer_id>/", views.farmer_statement),
    path("reports/<str:name>/", views.report_data),
]
