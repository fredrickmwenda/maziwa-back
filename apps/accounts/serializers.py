from rest_framework import serializers

from .constants import PERMISSIONS
from .models import Membership, Role


class RoleSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "kind", "permissions", "members"]
        read_only_fields = ["kind"]

    def get_members(self, r):
        return getattr(r, "n_members", None) if hasattr(r, "n_members") else r.memberships.count()

    def validate_permissions(self, value):
        bad = [c for c in value if c not in PERMISSIONS]
        if bad:
            raise serializers.ValidationError(f"Unknown permission: {', '.join(bad)}")
        return sorted(set(value))


class MemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.CharField(source="display_name", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    kind = serializers.CharField(source="role.kind", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "username", "full_name", "role", "role_name", "kind", "job_title", "phone",
                  "monthly_salary", "is_active"]
