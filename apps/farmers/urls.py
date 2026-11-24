from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("farmers", views.FarmerViewSet, basename="farmer")

urlpatterns = router.urls + [
    path("register/", views.register_farmer),
]
