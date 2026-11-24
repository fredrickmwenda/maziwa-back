from rest_framework import serializers

from .models import Notification, SmsLog


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"


class SmsLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsLog
        fields = ["id", "phone", "message", "kind", "status", "detail", "created"]
