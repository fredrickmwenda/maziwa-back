from django.contrib import admin

from .models import CollectionCentre, Route, RouteTrip, Transporter, TransporterPayment

for model in (CollectionCentre, Transporter, Route, RouteTrip, TransporterPayment):
    admin.site.register(model)
