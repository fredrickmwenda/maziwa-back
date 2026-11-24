from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("payroll", views.PayrollViewSet, basename="payroll")

urlpatterns = router.urls + [
]
