from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.permissions import require
from apps.accounts.services import get_or_create_user
from apps.tenants.models import Organization
from apps.tenants.services import check_capacity
from core.tenancy import TenantMixin

from .models import Farmer
from .serializers import FarmerSerializer


class FarmerViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Farmer.objects.select_related("route")
    serializer_class = FarmerSerializer
    permission_classes = [require("farmers.manage", "farmers.view")]
    farmer_lookup = "id"

    def perform_create(self, s):
        check_capacity(self.org)
        s.save()


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@transaction.atomic
def register_farmer(request):
    """Farmer self-registration using the dairy code. A farmer already in another dairy re-uses the same phone login."""
    org = get_object_or_404(Organization, slug=(request.data.get("org") or "").strip().lower())
    if not org.subscription_ok:
        raise PermissionDenied("This dairy is not accepting registrations right now.")
    check_capacity(org)
    s = FarmerSerializer(data=request.data, context={"org": org})
    s.is_valid(raise_exception=True)
    phone = s.validated_data["phone"]
    user = get_or_create_user(phone, request.data.get("password"), s.validated_data["full_name"])
    s.save(user=user)
    return Response({"ok": True}, status=201)
