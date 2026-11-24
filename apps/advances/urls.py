from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("advances", views.AdvanceViewSet, basename="advance")

urlpatterns = [path("advances/settings/", views.advance_settings)] + router.urls
