from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from . import security
from .constants import DEFAULT_ROLES
from .models import Role

User = get_user_model()


def create_default_roles(org):
    for name, kind, perms in DEFAULT_ROLES:
        Role.objects.get_or_create(organization=org, name=name, defaults=dict(kind=kind, permissions=perms))


def get_or_create_user(username, password, full_name="", must_change=False):
    """One login works across dairies: reuse the account if the password matches."""
    u = User.objects.filter(username=username).first()
    if u:
        if not u.check_password(password or ""):
            raise ValidationError({"detail": "That username already has an account. Enter its existing password to use it."})
        return u
    security.check_password_strength(password, User(username=username, first_name=full_name))
    u = User.objects.create_user(username=username, password=password, first_name=full_name)
    if must_change:
        security.set_must_change(u, True)
    return u
