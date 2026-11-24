from django.db import models

from apps.farmers.models import Farmer
from apps.tenants.models import Organization


class Notification(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=120)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]


class SmsLog(models.Model):
    SENT, FAILED, SKIPPED = "SENT", "FAILED", "SKIPPED"
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="sms_log")
    phone = models.CharField(max_length=20)
    message = models.CharField(max_length=480)
    kind = models.CharField(max_length=20, default="ALERT")
    status = models.CharField(max_length=10)
    detail = models.CharField(max_length=200, blank=True)
    cost = models.CharField(max_length=20, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
