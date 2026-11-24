from datetime import timedelta

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=40)
    price_kes = models.DecimalField(max_digits=10, decimal_places=2)
    max_farmers = models.PositiveIntegerField()
    sms_enabled = models.BooleanField(default=False)
    sms_quota = models.PositiveIntegerField(default=0, help_text="SMS per month")

    class Meta:
        ordering = ["price_kes"]

    def __str__(self):
        return self.name


class Organization(models.Model):
    """A tenant: one dairy / cooperative. All business data hangs off this."""
    TRIAL, ACTIVE, SUSPENDED = "TRIAL", "ACTIVE", "SUSPENDED"
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, help_text="Dairy code used at login")
    phone = models.CharField(max_length=20, blank=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, default=TRIAL)
    trial_ends = models.DateTimeField()
    paid_until = models.DateTimeField(null=True, blank=True)
    farmer_seq = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    @property
    def state(self):
        now = timezone.now()
        if self.status == self.SUSPENDED:
            return "suspended"
        if self.status == self.ACTIVE and self.paid_until and self.paid_until > now:
            return "active"
        if self.status == self.TRIAL and self.trial_ends > now:
            return "trial"
        return "expired"

    @property
    def subscription_ok(self):
        return self.state in ("trial", "active")

    @property
    def ends(self):
        return self.paid_until if self.status == self.ACTIVE else self.trial_ends

    def __str__(self):
        return self.name


class Invoice(models.Model):
    PENDING, PAID = "PENDING", "PAID"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invoices")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, default=PENDING)
    reference = models.CharField(max_length=60, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def mark_paid(self, reference=""):
        now = timezone.now()
        org = self.organization
        base = org.paid_until if (org.paid_until and org.paid_until > now) else now
        org.plan, org.status, org.paid_until = self.plan, Organization.ACTIVE, base + timedelta(days=30)
        org.save()
        self.status, self.paid_at, self.reference = self.PAID, now, reference
        self.save()
