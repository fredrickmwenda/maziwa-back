from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("payments", views.PaymentViewSet, basename="payment")
router.register("credit/payments", views.CreditPaymentViewSet, basename="creditpayment")

urlpatterns = router.urls + [
    path("credit/pay/", views.credit_pay),
    path("credit/cash/", views.credit_cash),
]
