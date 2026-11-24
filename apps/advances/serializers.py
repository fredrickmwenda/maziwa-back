from rest_framework import serializers

from .models import Advance, AdvanceSettings


class AdvanceSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Advance
        fields = ["id", "farmer", "farmer_name", "principal", "interest", "total_due", "amount_repaid", "balance",
                  "status", "reason", "note", "requested_at", "decided_at", "disbursed_at", "disburse_method", "reference"]
        read_only_fields = fields


class AdvanceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvanceSettings
        fields = ["enabled", "max_amount", "interest_percent"]
