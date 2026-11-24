from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from apps.collection.models import Route
from apps.accounts.constants import KIND_FARMER
from apps.accounts.models import Membership, Role
from apps.accounts.security import set_must_change, temp_password
from apps.notifications.sms import send_sms
from core.utils import normalize_phone

from .models import Farmer

User = get_user_model()


class FarmerSerializer(serializers.ModelSerializer):
    credit_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    route = serializers.PrimaryKeyRelatedField(queryset=Route.objects.all(), required=False, allow_null=True)
    route_name = serializers.CharField(source="route.name", read_only=True, default="")
    temp_password = serializers.SerializerMethodField()

    class Meta:
        model = Farmer
        fields = ["id", "member_no", "full_name", "phone", "national_id", "village", "route", "route_name",
                  "is_active", "joined", "credit_balance", "password", "temp_password"]
        read_only_fields = ["member_no", "is_active"]

    def get_temp_password(self, obj):
        return getattr(obj, "_temp_password", None)  # only present right after creation

    def validate_route(self, value):
        org = self.context.get("org")
        if value and org and value.organization_id != org.id:
            raise serializers.ValidationError("Not found.")
        return value

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e))

    @transaction.atomic
    def create(self, data):
        """Links an existing account with the same phone, or creates one with a one-time temporary password."""
        org = self.context["org"]
        user, pwd, temp = data.pop("user", None), data.pop("password", None), None
        if user is None:
            user = User.objects.filter(username=data["phone"]).first()
            if user is None:
                temp = pwd or temp_password()
                user = User.objects.create_user(username=data["phone"], password=temp, first_name=data["full_name"])
                set_must_change(user, not pwd)
        if Membership.objects.filter(user=user, organization=org).exists():
            raise serializers.ValidationError({"phone": "This person is already a member of this dairy."})
        role = Role.objects.get(organization=org, kind=KIND_FARMER)
        Membership.objects.create(user=user, organization=org, role=role, phone=data["phone"])
        farmer = Farmer.objects.create(user=user, organization=org, **data)
        if temp and not pwd:
            farmer._temp_password = temp
            text = (f"{org.name}: your Maziwa Cloud login is {data['phone']}, temporary password {temp}, "
                    f"dairy code {org.slug}. You will be asked to change it.")
            transaction.on_commit(lambda: send_sms(data["phone"], text, org=org, kind="LOGIN"))
        return farmer
