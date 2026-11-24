from rest_framework import serializers

from .models import Buyer, MilkSale


class BuyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buyer
        fields = "__all__"
        read_only_fields = ["organization"]


class MilkSaleSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source="buyer.name", read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = MilkSale
        fields = "__all__"
        read_only_fields = ["organization", "total", "amount_received", "recorded_by"]
