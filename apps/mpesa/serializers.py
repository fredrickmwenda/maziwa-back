from rest_framework import serializers

from .models import MpesaTransaction


class MpesaTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MpesaTransaction
        fields = ["id", "kind", "status", "phone", "amount", "receipt", "result_desc", "created", "completed"]
