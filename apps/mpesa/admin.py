from django.contrib import admin

from core.admin import ReadOnlyAdmin

from .models import MpesaConfig, MpesaTransaction

admin.site.register(MpesaTransaction)
admin.site.register(MpesaConfig, ReadOnlyAdmin)  # read-only in the admin
