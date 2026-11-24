from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from apps.accounts.permissions import require
from core.tenancy import TenantMixin, same_org

from .models import MilkCollection, MilkRate, QualityTier
from .serializers import MilkCollectionSerializer, MilkRateSerializer, QualityTierSerializer
from .services import load_tiers, notify_collection


class MilkCollectionViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = MilkCollection.objects.select_related("farmer", "route", "centre")
    serializer_class = MilkCollectionSerializer
    permission_classes = [require("milk.record", "milk.view")]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if "org" in ctx:
            ctx["tiers"] = load_tiers(ctx["org"])
        return ctx

    def perform_create(self, s):
        same_org(s.validated_data["farmer"], self.org, "farmer")
        route = s.validated_data["farmer"].route
        c = s.save(organization=self.org, recorded_by=self.request.user, route=route, centre=route.centre if route else None)
        notify_collection(c)


class MilkRateViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = MilkRate.objects.all()
    serializer_class = MilkRateSerializer
    permission_classes = [require("rates.manage", "milk.view")]
    farmer_lookup = None


class QualityTierViewSet(TenantMixin, viewsets.ModelViewSet):
    """Fat / protein bonus and penalty tiers."""
    queryset = QualityTier.objects.all()
    serializer_class = QualityTierSerializer
    permission_classes = [require("rates.manage", "milk.view")]
    farmer_lookup = None

    def perform_create(self, s):
        if QualityTier.objects.filter(organization=self.org, metric=s.validated_data["metric"],
                                      min_value=s.validated_data["min_value"]).exists():
            raise ValidationError({"min_value": "A tier at this level already exists."})
        s.save(organization=self.org)
