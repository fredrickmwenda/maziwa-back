from rest_framework import serializers

from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Expense
        fields = "__all__"
        read_only_fields = ["organization", "recorded_by", "payroll"]
