from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.payroll.models import PayrollEntry
from apps.tenants.models import Organization


EXPENSE_CATEGORIES = [
    ("FEED_PURCHASE", "Feed purchase"), ("TRANSPORT", "Transport"), ("FUEL", "Fuel"),
    ("REPAIRS", "Repairs and maintenance"), ("UTILITIES", "Utilities"), ("VET", "Veterinary"),
    ("COOLING", "Cooling and storage"), ("SALARIES", "Salaries"), ("OTHER", "Other"),
]


class Expense(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES, default="OTHER")
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    paid_to = models.CharField(max_length=100, blank=True)
    reference = models.CharField(max_length=60, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    payroll = models.OneToOneField(PayrollEntry, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="expense")

    class Meta:
        ordering = ["-date", "-id"]
