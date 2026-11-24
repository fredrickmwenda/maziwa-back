from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, Throttled, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.audit import services as audit
from apps.tenants.models import Organization, Plan
from apps.tenants.services import ensure_plans
from core.tenancy import TenantMixin

from . import security
from .constants import KIND_CUSTOM, KIND_FARMER, KIND_OWNER, PERMISSIONS
from .models import Membership, Role
from .permissions import require
from .serializers import MemberSerializer, RoleSerializer
from .services import create_default_roles, get_or_create_user

User = get_user_model()


class RoleViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Role.objects.annotate(n_members=Count("memberships"))
    serializer_class = RoleSerializer
    permission_classes = [require("team.manage", "team.manage")]
    farmer_lookup = None

    def _unique(self, name, exclude=None):
        qs = Role.objects.filter(organization=self.org, name__iexact=name)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        if qs.exists():
            raise ValidationError({"name": "A role with this name already exists."})

    def perform_create(self, s):
        self._unique(s.validated_data["name"])
        s.save(organization=self.org, kind=KIND_CUSTOM)

    def perform_update(self, s):
        if s.instance.kind != KIND_CUSTOM:
            raise PermissionDenied("Built-in roles cannot be changed.")
        if "name" in s.validated_data:
            self._unique(s.validated_data["name"], s.instance)
        s.save()

    def perform_destroy(self, r):
        if r.kind != KIND_CUSTOM:
            raise PermissionDenied("Built-in roles cannot be deleted.")
        if r.memberships.exists():
            raise ValidationError({"detail": "Move its members to another role first."})
        r.delete()


class MemberViewSet(TenantMixin, viewsets.ModelViewSet):
    """Dairy staff. An existing account (same username) is simply added to this dairy as well."""
    queryset = Membership.objects.exclude(role__kind=KIND_FARMER).select_related("user", "role")
    serializer_class = MemberSerializer
    permission_classes = [require("team.manage", "team.manage")]
    farmer_lookup = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _role(self, pk):
        r = get_object_or_404(Role, pk=pk, organization=self.org)
        if r.kind != KIND_CUSTOM:
            raise ValidationError({"role": "Choose one of the staff roles."})
        return r

    @transaction.atomic
    def create(self, request, *a, **kw):
        d = request.data
        username = (d.get("username") or "").strip().replace(" ", "")
        if not username:
            raise ValidationError({"username": "Required."})
        user = User.objects.filter(username=username).first() or get_or_create_user(
            username, d.get("password"), (d.get("full_name") or "").strip(), must_change=True)
        if Membership.objects.filter(user=user, organization=self.org).exists():
            raise ValidationError({"username": "Already a member of this dairy."})
        mem = Membership.objects.create(
            user=user, organization=self.org, role=self._role(d.get("role")),
            job_title=d.get("job_title", ""), phone=d.get("phone", ""),
            monthly_salary=d.get("monthly_salary") or 0)
        return Response(MemberSerializer(mem).data, status=201)

    def perform_update(self, s):
        inst, d = s.instance, s.validated_data
        if inst.role.kind == KIND_OWNER and ("role" in d or "is_active" in d):
            raise PermissionDenied("The owner's role and status cannot be changed.")
        if "role" in d:
            self._role(d["role"].pk)
        s.save()


@api_view(["GET"])
def permission_list(request):
    return Response([{"code": c, "label": l} for c, l in PERMISSIONS.items()])


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([security.LoginThrottle])
def login(request):
    name = security.clean_username(request.data.get("username"))
    if security.is_locked(name):
        audit.log("LOGIN_BLOCKED", "Login blocked: too many failures", actor=name)
        raise Throttled(wait=security.LOCK_MINUTES * 60, detail="Too many failed attempts. Try again in 15 minutes or reset your password by SMS.")
    user = authenticate(username=name, password=request.data.get("password") or "")
    if not user:
        audit.log("LOGIN_FAILED", "Wrong username or password", actor=name)
        raise ValidationError({"detail": "Wrong username or password."})
    audit.log("LOGIN", "Logged in", actor=user.username, user=user)
    return Response({"token": security.fresh_token(user).key})


@api_view(["POST"])
def logout(request):
    if request.auth:
        request.auth.delete()
    return Response({"ok": True})


@api_view(["POST"])
def change_password(request):
    u = request.user
    if not u.check_password(request.data.get("old_password") or ""):
        raise ValidationError({"detail": "Your current password is wrong."})
    security.check_password_strength(request.data.get("new_password"), u)
    u.set_password(request.data["new_password"])
    u.save()
    security.set_must_change(u, False)
    audit.log("PASSWORD_CHANGE", "Password changed", user=u)
    Token.objects.filter(user=u).exclude(pk=request.auth.pk).delete()  # sign out other devices
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([security.ResetThrottle])
def password_forgot(request):
    security.request_reset(request.data.get("username"))
    return Response({"detail": "If that account has a phone number, a 6-digit code was sent by SMS."})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([security.ResetThrottle])
def password_reset(request):
    security.confirm_reset(request.data.get("username"), request.data.get("code"), request.data.get("new_password"))
    return Response({"detail": "Password changed. You can log in now."})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@transaction.atomic
def signup(request):
    """A new dairy starts a free trial. An existing user can start a second dairy with the same login."""
    d = request.data
    name, username = (d.get("org_name") or "").strip(), (d.get("username") or "").strip().replace(" ", "")
    if not name or not username:
        raise ValidationError({"detail": "Dairy name and username are required."})
    user = get_or_create_user(username, d.get("password"), (d.get("full_name") or "").strip())
    ensure_plans()
    base = slugify(name)[:30] or "dairy"
    slug, n = base, 1
    while Organization.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}{n}"
    org = Organization.objects.create(name=name, slug=slug, phone=d.get("phone", ""),
                                      plan=Plan.objects.get(code="starter"),
                                      trial_ends=timezone.now() + timedelta(days=settings.TRIAL_DAYS))
    create_default_roles(org)
    Membership.objects.create(user=user, organization=org, role=Role.objects.get(organization=org, kind=KIND_OWNER))
    return Response({"org": slug, "username": username}, status=201)
