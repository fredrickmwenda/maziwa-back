from rest_framework import viewsets

from apps.accounts.permissions import require
from core.pagination import Pager
from core.tenancy import TenantMixin

from .models import AuditLog
from .serializers import AuditSerializer


class AuditViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditSerializer
    permission_classes = [require(None, "audit.view")]
    farmer_lookup = None
    pagination_class = Pager

    def get_queryset(self):
        qs, q = super().get_queryset(), self.request.query_params
        for field, lookup in (("model", "model"), ("actor", "actor__icontains"), ("action", "action"),
                              ("start", "created__date__gte"), ("end", "created__date__lte"), ("q", "summary__icontains")):
            if q.get(field):
                qs = qs.filter(**{lookup: q[field]})
        return qs
