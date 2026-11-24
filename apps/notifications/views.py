from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import allow, require
from core.pagination import Pager
from core.tenancy import TenantMixin

from .models import Notification, SmsLog
from .serializers import NotificationSerializer, SmsLogSerializer


class NotificationViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [require(None, "farmers.view")]
    org_lookup = "farmer__organization"

    @action(detail=False, methods=["post"], permission_classes=[allow()])
    def read_all(self, request):
        if self.m.role.kind == KIND_FARMER:  # staff never mark farmers' alerts
            self.get_queryset().update(is_read=True)
        return Response({"ok": True})


class SmsViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SmsLog.objects.all()
    serializer_class = SmsLogSerializer
    permission_classes = [require(None, "audit.view")]
    farmer_lookup = None
    pagination_class = Pager
