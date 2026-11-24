from decimal import Decimal

from django.db.models import Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import require
from core.tenancy import TenantMixin

from .models import Expense, EXPENSE_CATEGORIES
from .serializers import ExpenseSerializer


class ExpenseViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [require("expenses.manage", "expenses.view")]
    farmer_lookup = None

    def get_queryset(self):
        qs, q = super().get_queryset(), self.request.query_params
        if q.get("start"):
            qs = qs.filter(date__gte=q["start"])
        if q.get("end"):
            qs = qs.filter(date__lte=q["end"])
        if q.get("category"):
            qs = qs.filter(category=q["category"])
        return qs

    def perform_create(self, s):
        s.save(organization=self.org, recorded_by=self.request.user)

    def perform_update(self, s):
        if s.instance.payroll_id:
            raise ValidationError({"detail": "Salary expenses are created by payroll and cannot be edited."})
        s.save()

    def perform_destroy(self, i):
        if i.payroll_id:
            raise ValidationError({"detail": "Salary expenses are created by payroll and cannot be deleted."})
        i.delete()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        rows = self.get_queryset().values("category").annotate(total=Sum("amount")).order_by("-total")
        labels = dict(EXPENSE_CATEGORIES)
        return Response({"total": sum((r["total"] for r in rows), Decimal("0")),
                         "by_category": [{"category": r["category"], "label": labels[r["category"]],
                                          "total": r["total"]} for r in rows]})
