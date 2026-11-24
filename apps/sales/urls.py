from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("buyers", views.BuyerViewSet, basename="buyer")
router.register("sales", views.MilkSaleViewSet, basename="milksale")

urlpatterns = router.urls
