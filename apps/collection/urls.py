from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("centres", views.CentreViewSet, basename="centre")
router.register("transporters", views.TransporterViewSet, basename="transporter")
router.register("transporter-payments", views.TransporterPaymentViewSet, basename="transporterpayment")
router.register("routes", views.RouteViewSet, basename="route")
router.register("route-trips", views.RouteTripViewSet, basename="routetrip")

urlpatterns = router.urls
