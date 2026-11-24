from django.db import models

from apps.accounts.models import Membership
from apps.tenants.models import Organization


class PayrollEntry(models.Model):
    PENDING, PAID = "PENDING", "PAID"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payroll")
    member = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="payslips")
    month = models.DateField(help_text="First day of the pay month")
    basic = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, default=PENDING)
    reference = models.CharField(max_length=60, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("member", "month")
        ordering = ["-month", "member_id"]
