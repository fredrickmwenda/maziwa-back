from django.conf import settings
from django.db import models

from apps.tenants.models import Organization


class AuditLog(models.Model):
    """Append-only record of who did what. Never edited or deleted through the app."""
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=150, default="system")
    action = models.CharField(max_length=20)
    model = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip = models.CharField(max_length=45, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created", "-id"]
        indexes = [models.Index(fields=["organization", "-created"]), models.Index(fields=["actor", "action", "created"])]
