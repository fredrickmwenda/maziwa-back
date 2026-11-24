from django.contrib import admin

from .models import Invoice, Organization, Plan

admin.site.register(Plan)
admin.site.register(Organization)
admin.site.register(Invoice)
