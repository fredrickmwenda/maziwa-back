from django.urls import path

from . import views

urlpatterns = [
    path("billing/", views.billing),
    path("billing/subscribe/", views.subscribe),
]
