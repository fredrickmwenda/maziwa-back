"""Audit write helper."""
from django.conf import settings

from .context import ctx          # re-exported for callers that already import from services
from .models import AuditLog

__all__ = ["ctx", "client_ip", "log"]


def client_ip(request):
    if settings.TRUST_PROXY:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log(action, summary="", *, org_id=None, instance=None, changes=None, actor=None, user=None):
    c = ctx.get() or {}
    user = user or c.get("user")
    AuditLog.objects.create(
        organization_id=org_id, user=user, actor=actor or (user.username if user else "system"),
        action=action, model=instance._meta.model_name if instance is not None else "",
        object_id=str(instance.pk) if instance is not None else "", summary=summary[:250],
        changes=changes or {}, ip=c.get("ip") or "")
