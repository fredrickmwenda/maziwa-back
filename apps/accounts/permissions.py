"""Membership lookup and the DRF permission classes used by all apps."""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import AccountSecurity, Membership


def membership(request):
    """The caller's membership in the dairy named by the X-Dairy header
    (or their only dairy). Cached per request."""
    if hasattr(request, "_membership"):
        return request._membership
    m, u = None, request.user
    if u and u.is_authenticated:
        qs = Membership.objects.filter(user=u, is_active=True).select_related(
            "organization__plan", "role")
        slug = request.headers.get("X-Dairy")
        if slug:
            m = qs.filter(organization__slug=slug).first()
        elif qs.count() == 1:
            m = qs.first()
    request._membership = m
    return m


def must_change_password(request):
    if not hasattr(request, "_mcp"):
        request._mcp = AccountSecurity.objects.filter(user=request.user, must_change_password=True).exists()
    return request._mcp


def require(write=None, read=None):
    """Permission class: `read` code for GET, `write` code for changes (plus a live subscription).
    None means any member of the dairy."""
    class P(BasePermission):
        message = "You do not have permission to do this."

        def has_permission(self, request, view):
            m = membership(request)
            if m is None:
                self.message = "Choose a dairy first."
                return False
            if must_change_password(request):
                self.message = "Set a new password first."
                return False
            if request.method in SAFE_METHODS:
                need = read
            else:
                if not m.organization.subscription_ok:
                    self.message = "Subscription expired. The dairy owner must renew under Billing."
                    return False
                need = write
            return need is None or m.has(need)
    return P


def allow(code=None):
    """Like require() but ignores the subscription state (billing, marking alerts read)."""
    class P(BasePermission):
        message = "You do not have permission to do this."

        def has_permission(self, request, view):
            m = membership(request)
            return m is not None and not must_change_password(request) and (code is None or m.has(code))
    return P


class PlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_superuser)
