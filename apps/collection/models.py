from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.tenants.models import Organization


class CollectionCentre(models.Model):
    """Where milk is bulked and cooled before it is sold."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="centres")
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    has_cooling = models.BooleanField(default=True)
    capacity_litres = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Transporter(models.Model):
    """Person or company that carries milk from farmers to a centre."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="transporters")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    id_number = models.CharField(max_length=20, blank=True)
    vehicle_reg = models.CharField(max_length=20, blank=True)
    rate_per_litre = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="Pay per litre carried")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Route(models.Model):
    """A pick-up round: the farmers on it, the centre it delivers to and the usual transporter."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="routes")
    name = models.CharField(max_length=80)
    centre = models.ForeignKey(CollectionCentre, null=True, blank=True, on_delete=models.SET_NULL, related_name="routes")
    transporter = models.ForeignKey(Transporter, null=True, blank=True, on_delete=models.SET_NULL, related_name="routes")
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class RouteTrip(models.Model):
    """A route sheet: one route, one day, one session. Milk collected on it is compared with what the centre receives."""
    OPEN, RECEIVED = "OPEN", "RECEIVED"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="trips")
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="trips")
    date = models.DateField(default=timezone.localdate)
    session = models.CharField(max_length=2, choices=[("AM", "Morning"), ("PM", "Evening")])
    transporter = models.ForeignKey(Transporter, null=True, blank=True, on_delete=models.SET_NULL, related_name="trips")
    vehicle_reg = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=8, default=OPEN)
    received_litres = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Measured at the centre")
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = ("route", "date", "session")
        ordering = ["-date", "session", "route_id"]


class TransporterPayment(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="transporter_payments")
    transporter = models.ForeignKey(Transporter, on_delete=models.PROTECT, related_name="payments")
    period_start = models.DateField()
    period_end = models.DateField()
    litres = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=6, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=60, blank=True)
    expense = models.OneToOneField("expenses.Expense", null=True, blank=True, on_delete=models.SET_NULL, related_name="transporter_payment")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end", "-id"]
