from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("animals", views.AnimalViewSet, basename="animal")
router.register("health-events", views.HealthEventViewSet, basename="healthevent")
router.register("yields", views.YieldViewSet, basename="yield")

urlpatterns = router.urls + [
    path("herd/withdrawals/", views.withdrawals),
    path("herd/due/", views.due),
]
