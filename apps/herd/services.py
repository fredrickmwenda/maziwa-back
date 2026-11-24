from datetime import timedelta

from django.utils import timezone

from apps.expenses.models import Expense

GESTATION_DAYS = 283


def summarize(events):
    """Breeding and withdrawal summary from an animal's events (newest first)."""
    calving = next((e.date for e in events if e.kind == "CALVING"), None)
    ai = next((e for e in events if e.kind == "AI_SERVICE"), None)
    expected = ai.date + timedelta(days=GESTATION_DAYS) if ai and (not calving or calving < ai.date) else None
    withdrawal = max((e.withdrawal_ends for e in events if e.withdrawal_ends), default=None)
    if withdrawal and withdrawal < timezone.localdate():
        withdrawal = None
    return {"last_calving": calving, "last_ai": ai.date if ai else None, "expected_calving": expected,
            "withdrawal_until": withdrawal}


def post_vet_expense(event, user):
    """The dairy paid the vet: record it as a Veterinary expense."""
    exp = Expense.objects.create(
        organization=event.animal.farmer.organization, category="VET", amount=event.cost, date=event.date,
        description=f"{event.get_kind_display()}: {event.animal.tag} ({event.animal.farmer.full_name})"[:200],
        paid_to=event.vet_name, recorded_by=user)
    event.expense = exp
    event.save(update_fields=["expense"])
    return exp
