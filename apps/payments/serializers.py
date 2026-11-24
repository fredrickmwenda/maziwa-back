from rest_framework import serializers

from .models import CreditPayment, Payment


class PaymentSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)
    items = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = "__all__"

    def get_items(self, p):
        feed = [{"kind": "FEED", "product": i.order.product.name, "amount": i.amount}
                for i in p.items.select_related("order__product")]
        adv = [{"kind": "ADVANCE", "product": f"Advance #{i.advance_id}", "amount": i.amount} for i in p.advance_items.all()]
        return feed + adv


class CreditPaymentSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)

    class Meta:
        model = CreditPayment
        fields = ["id", "farmer", "farmer_name", "amount", "method", "reference", "created"]
