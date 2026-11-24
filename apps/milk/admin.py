from django.contrib import admin

from .models import MilkCollection, MilkRate, QualityTier

admin.site.register(MilkRate)
admin.site.register(MilkCollection)
admin.site.register(QualityTier)
