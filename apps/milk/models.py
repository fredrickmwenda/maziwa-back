from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.farmers.models import Farmer
from apps.tenants.models import Organization

REJECT_REASONS = [("ALCOHOL", "Failed alcohol test"), ("ADULTERATED", "Adulterated / watered"),
                  ("SPOILT", "Sour or spoilt"), ("TEMPERATURE", "Too warm"), ("OTHER", "Other")]


class MilkRate(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="rates")
    price_per_litre = models.DecimalField(max_digits=8, decimal_places=2)
    effective_from = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-effective_from", "-id"]

    @classmethod
    def current(cls, org):
        r = cls.objects.filter(organization=org).first()
        return r.price_per_litre if r else Decimal("0")


class QualityTier(models.Model):
    """Price adjustment per litre once fat or protein reaches `min_value`. The highest tier reached wins.
    A negative bonus is a penalty (for example fat below 3.2%)."""
    FAT, PROTEIN = "FAT", "PROTEIN"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="quality_tiers")
    metric = models.CharField(max_length=8, choices=[(FAT, "Fat %"), (PROTEIN, "Protein %")])
    min_value = models.DecimalField(max_digits=4, decimal_places=2)
    bonus_per_litre = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        unique_together = ("organization", "metric", "min_value")
        ordering = ["metric", "min_value"]


class MilkCollection(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="collections")
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="collections")
    date = models.DateField(default=timezone.localdate)
    session = models.CharField(max_length=2, choices=[("AM", "Morning"), ("PM", "Evening")])
    litres = models.DecimalField(max_digits=7, decimal_places=2, help_text="Litres delivered")
    fat_percent = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    protein_percent = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    alcohol_passed = models.BooleanField(default=True)
    rejected_litres = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    reject_reason = models.CharField(max_length=12, blank=True, choices=REJECT_REASONS)
    trip = models.ForeignKey("collection.RouteTrip", null=True, blank=True, on_delete=models.SET_NULL, related_name="collections")
    route = models.ForeignKey("collection.Route", null=True, blank=True, on_delete=models.SET_NULL, related_name="collections")
    centre = models.ForeignKey("collection.CollectionCentre", null=True, blank=True, on_delete=models.SET_NULL, related_name="collections")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("farmer", "date", "session")
        ordering = ["-date", "-session"]

    @property
    def accepted_litres(self):
        """Litres that are paid for."""
        return self.litres - self.rejected_litres
