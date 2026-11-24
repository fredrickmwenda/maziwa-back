"""Login throttling and lockout, password rules and password reset by SMS."""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import AnonRateThrottle

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.notifications.sms import send_sms
from core.utils import normalize_phone

from .models import AccountSecurity, Membership, PasswordResetCode

User = get_user_model()


LOCK_AFTER, LOCK_MINUTES = 5, 15


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class ResetThrottle(AnonRateThrottle):
    scope = "reset"


def clean_username(raw):
    name = (raw or "").strip()
    if re.fullmatch(r"\+?[\d\s-]{9,15}", name):  # farmers log in with their phone, any format
        try:
            return normalize_phone(name)
        except ValueError:
            pass
    return name


def is_locked(username):
    since = timezone.now() - timedelta(minutes=LOCK_MINUTES)
    fails = AuditLog.objects.filter(action="LOGIN_FAILED", actor=username, created__gte=since)
    ok = AuditLog.objects.filter(action="LOGIN", actor=username, created__gte=since).order_by("-created").first()
    if ok:
        fails = fails.filter(created__gt=ok.created)
    return fails.count() >= LOCK_AFTER


def fresh_token(user):
    tok = Token.objects.filter(user=user).first()
    if tok and tok.created < timezone.now() - timedelta(days=settings.TOKEN_TTL_DAYS):
        tok.delete()
        tok = None
    if tok is None:
        tok = Token.objects.create(user=user)
    return tok


def check_password_strength(password, user=None):
    try:
        validate_password(password or "", user)
    except DjangoValidationError as e:
        raise ValidationError({"password": list(e.messages)})


def temp_password():
    return "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(8))


def set_must_change(user, flag=True):
    AccountSecurity.objects.update_or_create(user=user, defaults={"must_change_password": flag})


def _user_phone(user):
    m = Membership.objects.filter(user=user).exclude(phone="").values_list("phone", flat=True).first()
    return m or user.farmer_profiles.values_list("phone", flat=True).first()


def _hash(user, code):
    return hashlib.sha256(f"{settings.SECRET_KEY}:{user.pk}:{code}".encode()).hexdigest()


def request_reset(username):
    """Always looks the same to the caller (no hint whether the account exists)."""
    user = User.objects.filter(username=clean_username(username), is_active=True).first()
    phone = _user_phone(user) if user else None
    if not user or not phone:
        return
    hour_ago = timezone.now() - timedelta(hours=1)
    if PasswordResetCode.objects.filter(user=user, created__gte=hour_ago).count() >= 3:
        return
    code = f"{secrets.randbelow(900000) + 100000}"
    PasswordResetCode.objects.create(user=user, code_hash=_hash(user, code),
                                     expires_at=timezone.now() + timedelta(minutes=10))
    send_sms(phone, f"Maziwa Cloud code: {code}. Valid 10 minutes. Never share it.", kind="OTP", bypass_plan=True)
    audit.log("RESET_REQUEST", "Password reset code sent", actor=user.username, user=user)


def confirm_reset(username, code, new_password):
    bad = ValidationError({"detail": "That code is wrong or has expired."})
    user = User.objects.filter(username=clean_username(username), is_active=True).first()
    if not user:
        raise bad
    rc = (PasswordResetCode.objects.filter(user=user, used=False, expires_at__gt=timezone.now())
          .order_by("-created").first())
    if not rc or rc.attempts >= 5:
        raise bad
    rc.attempts += 1
    rc.save(update_fields=["attempts"])
    if not hmac.compare_digest(rc.code_hash, _hash(user, str(code).strip())):
        raise bad
    check_password_strength(new_password, user)
    user.set_password(new_password)
    user.save()
    rc.used = True
    rc.save(update_fields=["used"])
    set_must_change(user, False)
    Token.objects.filter(user=user).delete()  # sign out everywhere
    audit.log("PASSWORD_RESET", "Password reset by SMS code", actor=user.username, user=user)
