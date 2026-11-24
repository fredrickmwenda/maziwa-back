"""Run daily:  python manage.py send_herd_reminders"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.herd.models import HealthEvent
from apps.notifications.services import notify


class Command(BaseCommand):
    help = "Notify farmers (in-app, and SMS on paid plans) about vaccinations and checks due in 3 days."

    def handle(self, *args, **opts):
        target = timezone.localdate() + timedelta(days=3)
        events = HealthEvent.objects.filter(next_due=target).select_related("animal__farmer__organization")
        for e in events:
            notify(e.animal.farmer, "Herd reminder", f"{e.get_kind_display()} due for {e.animal.tag} on {e.next_due}. {e.description}".strip())
        self.stdout.write(f"{events.count()} reminder(s) sent")
