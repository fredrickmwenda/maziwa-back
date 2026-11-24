from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("roles", views.RoleViewSet, basename="role")
router.register("members", views.MemberViewSet, basename="member")

urlpatterns = router.urls + [
    path("login/", views.login),
    path("logout/", views.logout),
    path("signup/", views.signup),
    path("permissions/", views.permission_list),
    path("password/change/", views.change_password),
    path("password/forgot/", views.password_forgot),
    path("password/reset/", views.password_reset),
]
