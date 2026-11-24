from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .context import ctx          # ← was: from .services import ctx


class AuditTokenAuthentication(TokenAuthentication):
    """Token login with an expiry; also tells the audit log who the caller is."""
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token.created < timezone.now() - timedelta(days=settings.TOKEN_TTL_DAYS):
            token.delete()
            raise AuthenticationFailed("Session expired. Please log in again.")
        c = ctx.get()
        if c is not None:
            c["user"] = user
        return user, token
