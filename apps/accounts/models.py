from django.conf import settings
from django.db import models

from apps.tenants.models import Organization

from .constants import KIND_CUSTOM, KIND_OWNER, PERMISSIONS


class Role(models.Model):
    """Each dairy owns its roles. Owner and Farmer are built in; the owner creates any others."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, default=KIND_CUSTOM)
    permissions = models.JSONField(default=list)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["id"]

    def __str__(self):
        return f"{self.organization.name}: {self.name}"


class Membership(models.Model):
    """A person (user) inside one dairy. One user can have a membership in many dairies."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    job_title = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=20, blank=True, help_text="For salary payment")
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    joined = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "organization")

    def has(self, code):
        return self.role.kind == KIND_OWNER or code in (self.role.permissions or [])

    @property
    def perms(self):
        return list(PERMISSIONS) if self.role.kind == KIND_OWNER else list(self.role.permissions or [])

    @property
    def farmer(self):
        if not hasattr(self, "_farmer"):
            self._farmer = self.user.farmer_profiles.filter(organization_id=self.organization_id).first()
        return self._farmer

    @property
    def display_name(self):
        return self.user.first_name or self.user.username


class AccountSecurity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security")
    must_change_password = models.BooleanField(default=False)


class PasswordResetCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
