from django.contrib import admin

from core.admin import ReadOnlyAdmin

from .models import AuditLog

admin.site.register(AuditLog, ReadOnlyAdmin)  # read-only in the admin
