from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import require
from core.tenancy import TenantMixin, same_org

from .models import Buyer, MilkSale
from .serializers import BuyerSerializer, MilkSaleSerializer


class BuyerViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Buyer.objects.all()
    serializer_class = BuyerSerializer
    permission_classes = [require("sales.manage", "sales.view")]
    farmer_lookup = None


class MilkSaleViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = MilkSale.objects.select_related("buyer")
    serializer_class = MilkSaleSerializer
    permission_classes = [require("sales.manage", "sales.view")]
    farmer_lookup = None

    def get_queryset(self):
        qs, q = super().get_queryset(), self.request.query_params
        if q.get("start"):
            qs = qs.filter(date__gte=q["start"])
        if q.get("end"):
            qs = qs.filter(date__lte=q["end"])
        if q.get("buyer"):
            qs = qs.filter(buyer_id=q["buyer"])
        return qs

    def perform_create(self, s):
        same_org(s.validated_data["buyer"], self.org, "buyer")
        d = s.validated_data
        if d["litres"] <= 0 or d["price_per_litre"] <= 0:
            raise ValidationError({"litres": "Litres and price must be above zero."})
        s.save(organization=self.org, recorded_by=self.request.user, total=(d["litres"] * d["price_per_litre"]).quantize(Decimal("0.01")))

    def perform_update(self, s):
        sale = s.instance
        litres = s.validated_data.get("litres", sale.litres)
        price = s.validated_data.get("price_per_litre", sale.price_per_litre)
        total = (litres * price).quantize(Decimal("0.01"))
        if total < sale.amount_received:
            raise ValidationError({"litres": "The total cannot be less than the money already received."})
        s.save(total=total)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def receive(self, request, pk=None):
        """The buyer paid (part of) this invoice: {"amount": 50000, "reference": "..."}."""
        sale = MilkSale.objects.select_for_update().get(pk=self.get_object().pk)
        try:
            amount = Decimal(str(request.data.get("amount")))
        except InvalidOperation:
            raise ValidationError({"amount": "Enter a valid amount."})
        if amount <= 0 or amount > sale.balance:
            raise ValidationError({"amount": f"Enter an amount up to the balance of KES {sale.balance}."})
        sale.amount_received += amount
        if request.data.get("reference"):
            sale.reference = str(request.data["reference"])[:60]
        sale.save(update_fields=["amount_received", "reference"])
        return Response(MilkSaleSerializer(sale).data)
