from decimal import Decimal

from django.conf import settings
from django.db import models, transaction

from apps.tenants.models import Organization


class Farmer(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="farmers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="farmer_profiles")
    member_no = models.CharField(max_length=20, blank=True)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, help_text="e.g. 2547XXXXXXXX")
    national_id = models.CharField(max_length=20, blank=True)
    village = models.CharField(max_length=80, blank=True)
    route = models.ForeignKey("collection.Route", null=True, blank=True, on_delete=models.SET_NULL, related_name="farmers")
    is_active = models.BooleanField(default=True)
    joined = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = (("organization", "member_no"), ("organization", "user"))

    def save(self, *a, **kw):
        if not self.member_no:
            with transaction.atomic():
                org = Organization.objects.select_for_update().get(pk=self.organization_id)
                org.farmer_seq += 1
                org.save(update_fields=["farmer_seq"])
                self.member_no = f"F{org.farmer_seq:05d}"
                return super().save(*a, **kw)
        return super().save(*a, **kw)

    def credit_balance(self):
        return sum((o.balance for o in self.orders.all()), Decimal("0"))

    def __str__(self):
        return f"{self.member_no} {self.full_name}"
