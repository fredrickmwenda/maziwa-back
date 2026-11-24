from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("sms", views.SmsViewSet, basename="sms")

urlpatterns = router.urls + [
]
