from django.conf import settings
from django.db import models

from apps.advances.models import Advance
from apps.farmers.models import Farmer
from apps.store.models import CreditOrder
from apps.tenants.models import Organization


class Payment(models.Model):
    PENDING, PAID = "PENDING", "PAID"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payments")
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="payments")
    period_start = models.DateField()
    period_end = models.DateField()
    litres = models.DecimalField(max_digits=10, decimal_places=2, help_text="Accepted litres")
    rejected_litres = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rate = models.DecimalField(max_digits=8, decimal_places=2)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Quality bonus (or penalty) included in gross")
    gross = models.DecimalField(max_digits=12, decimal_places=2)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Feed credit + advances")
    advance_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, default=PENDING)
    reference = models.CharField(max_length=60, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_end", "-id"]


class PaymentDeduction(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="items")
    order = models.ForeignKey(CreditOrder, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)


class AdvanceDeduction(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="advance_items")
    advance = models.ForeignKey(Advance, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)


class CreditPayment(models.Model):
    """A farmer repaying feed credit outside the milk payment (cash or M-Pesa)."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="credit_payments")
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="credit_payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, default="CASH")
    reference = models.CharField(max_length=60, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
