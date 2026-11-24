from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.tenants.models import Organization


class Buyer(models.Model):
    """A processor or customer that buys the dairy's milk (Brookside, New KCC, ...)."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="buyers")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class MilkSale(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="milk_sales")
    buyer = models.ForeignKey(Buyer, on_delete=models.PROTECT, related_name="sales")
    date = models.DateField(default=timezone.localdate)
    litres = models.DecimalField(max_digits=10, decimal_places=2)
    price_per_litre = models.DecimalField(max_digits=8, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    amount_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reference = models.CharField(max_length=60, blank=True, help_text="Delivery note / invoice number")
    notes = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]

    @property
    def balance(self):
        return self.total - self.amount_received

    @property
    def status(self):
        if self.balance <= Decimal("0"):
            return "PAID"
        return "PART" if self.amount_received > 0 else "UNPAID"
