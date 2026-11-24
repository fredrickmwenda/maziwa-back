from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.farmers.models import Farmer


class Animal(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="animals")
    tag = models.CharField(max_length=30)
    name = models.CharField(max_length=60, blank=True)
    breed = models.CharField(max_length=60, blank=True)
    sex = models.CharField(max_length=1, default="F", choices=[("F", "Female"), ("M", "Male")])
    date_of_birth = models.DateField(null=True, blank=True)
    is_milking = models.BooleanField(default=True)
    status = models.CharField(max_length=8, default="ACTIVE", choices=[("ACTIVE", "Active"), ("SOLD", "Sold"), ("DEAD", "Dead")])

    class Meta:
        unique_together = ("farmer", "tag")
        ordering = ["farmer_id", "tag"]

    def __str__(self):
        return f"{self.tag} {self.name}".strip()


class HealthEvent(models.Model):
    """Vaccination, treatment, AI/breeding, pregnancy check, calving... for one animal."""
    VACCINATION, TREATMENT, DEWORMING, AI_SERVICE, PREGNANCY_CHECK, CALVING, OTHER = (
        "VACCINATION", "TREATMENT", "DEWORMING", "AI_SERVICE", "PREGNANCY_CHECK", "CALVING", "OTHER")
    KINDS = [(VACCINATION, "Vaccination"), (TREATMENT, "Treatment"), (DEWORMING, "Deworming"),
             (AI_SERVICE, "AI / service"), (PREGNANCY_CHECK, "Pregnancy check"), (CALVING, "Calving"), (OTHER, "Other")]
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=16, choices=KINDS)
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=200, blank=True, help_text="Drug, disease, bull/semen, result...")
    vet_name = models.CharField(max_length=80, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    withdrawal_days = models.PositiveSmallIntegerField(default=0, help_text="Days the milk must not be sold")
    withdrawal_ends = models.DateField(null=True, blank=True)
    next_due = models.DateField(null=True, blank=True, help_text="Next vaccination / check due")
    calf_tag = models.CharField(max_length=30, blank=True)
    calf_sex = models.CharField(max_length=1, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    expense = models.OneToOneField("expenses.Expense", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="health_event")

    class Meta:
        ordering = ["-date", "-id"]


class AnimalMilkRecord(models.Model):
    """Milk from one cow at one milking, for per-cow production."""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="yields")
    date = models.DateField(default=timezone.localdate)
    session = models.CharField(max_length=2, choices=[("AM", "Morning"), ("PM", "Evening")])
    litres = models.DecimalField(max_digits=6, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("animal", "date", "session")
        ordering = ["-date", "-session"]
