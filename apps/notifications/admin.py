from django.contrib import admin

from .models import Notification, SmsLog

admin.site.register(Notification)
admin.site.register(SmsLog)
