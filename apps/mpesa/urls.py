from django.urls import path

from . import views

urlpatterns = [
    path("mpesa/config/", views.mpesa_config),
    path("mpesa/transactions/", views.mpesa_transactions),
    path("mpesa/transactions/<int:pk>/status/", views.mpesa_status),
    path("mpesa/stk/<str:secret>/", views.stk_callback),
    path("mpesa/b2c-result/<str:secret>/", views.b2c_result),
    path("mpesa/b2c-timeout/<str:secret>/", views.b2c_timeout),
    path("billing/pay/", views.billing_pay),
]
