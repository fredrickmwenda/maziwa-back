from decimal import Decimal

from django.utils import timezone

from apps.notifications.services import notify

from .models import Advance, AdvanceSettings


def get_settings(org):
    return AdvanceSettings.objects.get_or_create(organization=org)[0]


def outstanding(farmer):
    """What the farmer owes now plus what is already promised (pending requests)."""
    total = Decimal("0")
    for a in Advance.objects.filter(farmer=farmer).exclude(status__in=[Advance.CLEARED, Advance.REJECTED]):
        total += a.balance if a.status == Advance.DISBURSED else a.principal
    return total


def request_advance(farmer, amount, reason=""):
    cfg = get_settings(farmer.organization)
    if not cfg.enabled:
        raise ValueError("Advances are not available at this dairy.")
    try:
        amount = Decimal(str(amount))
    except Exception:
        raise ValueError("Enter a valid amount.")
    if amount <= 0:
        raise ValueError("Enter an amount above zero.")
    owed = outstanding(farmer)
    if owed + amount > cfg.max_amount:
        raise ValueError(f"The most that can be outstanding is KES {cfg.max_amount}. This farmer already has KES {owed}.")
    interest = (amount * cfg.interest_percent / 100).quantize(Decimal("0.01"))
    return Advance.objects.create(organization=farmer.organization, farmer=farmer, principal=amount, interest=interest,
                                  total_due=amount + interest, reason=reason[:200])


def decide(advance, approve, user, note=""):
    if advance.status != Advance.REQUESTED:
        raise ValueError("This request has already been decided.")
    advance.status = Advance.APPROVED if approve else Advance.REJECTED
    advance.decided_by, advance.decided_at, advance.note = user, timezone.now(), note[:200]
    advance.save()
    if approve:
        notify(advance.farmer, "Advance approved", f"Your advance of KES {advance.principal} was approved and will be sent to you.")
    else:
        notify(advance.farmer, "Advance declined", f"Your advance request of KES {advance.principal} was declined. {note}".strip())
    return advance


def mark_disbursed(advance, method, reference="", user=None):
    """Money has been paid to the farmer (cash, bank, or M-Pesa confirmed)."""
    if advance.status not in (Advance.APPROVED, Advance.PROCESSING):
        raise ValueError("Only an approved advance can be paid out.")
    advance.status, advance.disbursed_at = Advance.DISBURSED, timezone.now()
    advance.disburse_method, advance.reference = method[:10], reference[:60]
    advance.save()
    notify(advance.farmer, "Advance paid",
           f"KES {advance.principal} sent to you ({method.title()}). KES {advance.total_due} will be taken from your milk payments. Ref: {reference}")
    return advance
