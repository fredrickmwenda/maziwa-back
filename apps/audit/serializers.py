from rest_framework import serializers

from .models import AuditLog


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "actor", "action", "model", "object_id", "summary", "changes", "ip", "created"]
