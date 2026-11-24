from django.contrib import admin

from .models import Animal, AnimalMilkRecord, HealthEvent

admin.site.register(Animal)
admin.site.register(HealthEvent)
admin.site.register(AnimalMilkRecord)
