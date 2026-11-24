from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.farmers.models import Farmer
from apps.tenants.models import Organization


class AdvanceSettings(models.Model):
    """Each dairy's rules for cash advances and loans."""
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="advance_settings")
    enabled = models.BooleanField(default=True)
    max_amount = models.DecimalField(max_digits=10, decimal_places=2, default=5000,
                                     help_text="Most a farmer may owe (including pending requests)")
    interest_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                           help_text="One-off fee added to each advance")


class Advance(models.Model):
    """Money lent to a farmer against future milk. Recovered from milk payments after feed credit."""
    REQUESTED, APPROVED, PROCESSING, DISBURSED, CLEARED, REJECTED = (
        "REQUESTED", "APPROVED", "PROCESSING", "DISBURSED", "CLEARED", "REJECTED")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="advances")
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="advances")
    principal = models.DecimalField(max_digits=10, decimal_places=2)
    interest = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_repaid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=12, default=REQUESTED)
    reason = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=200, blank=True, help_text="Reason for rejection or approval note")
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    disburse_method = models.CharField(max_length=10, blank=True)
    reference = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    @property
    def balance(self):
        """Still to be recovered (only once the money has been paid out)."""
        if self.status in (self.DISBURSED, self.CLEARED):
            return self.total_due - self.amount_repaid
        return Decimal("0")
