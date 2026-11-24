from rest_framework import serializers

from .models import PayrollEntry


class PayrollSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.display_name", read_only=True)
    role_name = serializers.CharField(source="member.role.name", read_only=True)

    class Meta:
        model = PayrollEntry
        fields = ["id", "member", "member_name", "role_name", "month", "basic", "allowances",
                  "deductions", "net", "status", "reference", "paid_at"]
        read_only_fields = ["member", "month", "basic", "net", "status", "reference", "paid_at"]
