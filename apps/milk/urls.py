from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("collections", views.MilkCollectionViewSet, basename="collection")
router.register("rates", views.MilkRateViewSet, basename="rate")
router.register("quality-tiers", views.QualityTierViewSet, basename="qualitytier")

urlpatterns = router.urls + [
]
