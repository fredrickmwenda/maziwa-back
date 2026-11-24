from django.utils import timezone

from apps.expenses.models import Expense

from .models import PayrollEntry


def finalize_payroll(entry, reference="", user=None):
    if entry.status == PayrollEntry.PAID:
        return entry
    entry.status, entry.paid_at, entry.reference = PayrollEntry.PAID, timezone.now(), reference
    entry.save()
    Expense.objects.create(organization=entry.organization, category="SALARIES", amount=entry.net, payroll=entry,
                           description=f"Salary {entry.member.display_name} {entry.month:%b %Y}",
                           paid_to=entry.member.display_name, reference=reference, recorded_by=user)
    return entry
