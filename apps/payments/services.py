from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.advances.models import Advance
from apps.milk.models import MilkCollection, MilkRate
from apps.milk.services import bonus_rate, load_tiers
from apps.notifications.services import notify
from apps.store.models import CreditOrder

from .models import AdvanceDeduction, CreditPayment, Payment, PaymentDeduction


@transaction.atomic
def generate_payment(farmer, start, end):
    """Accepted litres x (price + quality bonus), minus feed credit, then minus advances.
    Oldest debts first, never below zero; anything left over carries forward."""
    org = farmer.organization
    if Payment.objects.filter(farmer=farmer, period_start__lte=end, period_end__gte=start).exists():
        return None
    cols = list(MilkCollection.objects.filter(farmer=farmer, date__range=(start, end)))
    accepted = sum((c.accepted_litres for c in cols), Decimal("0"))
    rejected = sum((c.rejected_litres for c in cols), Decimal("0"))
    if accepted <= 0:
        return None
    rate, tiers = MilkRate.current(org), load_tiers(org)
    bonus = sum((c.accepted_litres * bonus_rate(tiers, c.fat_percent, c.protein_percent) for c in cols),
                Decimal("0")).quantize(Decimal("0.01"))
    gross = max((accepted * rate + bonus).quantize(Decimal("0.01")), Decimal("0"))

    remaining, feed_ded, feed_items = gross, Decimal("0"), []
    for o in (CreditOrder.objects.select_for_update()
              .filter(farmer=farmer, amount_paid__lt=F("total_cost")).order_by("created")):
        if remaining <= 0:
            break
        take = min(o.balance, remaining)
        o.amount_paid += take
        o.save(update_fields=["amount_paid"])
        feed_items.append((o, take))
        remaining -= take
        feed_ded += take

    adv_ded, adv_items = Decimal("0"), []
    for a in Advance.objects.select_for_update().filter(farmer=farmer, status=Advance.DISBURSED).order_by("disbursed_at"):
        if remaining <= 0:
            break
        take = min(a.balance, remaining)
        if take <= 0:
            continue
        a.amount_repaid += take
        if a.balance <= 0:
            a.status = Advance.CLEARED
        a.save(update_fields=["amount_repaid", "status"])
        adv_items.append((a, take))
        remaining -= take
        adv_ded += take

    p = Payment.objects.create(organization=org, farmer=farmer, period_start=start, period_end=end, litres=accepted,
                               rejected_litres=rejected, rate=rate, bonus=bonus, gross=gross,
                               deductions=feed_ded + adv_ded, advance_deductions=adv_ded, net=gross - feed_ded - adv_ded)
    PaymentDeduction.objects.bulk_create([PaymentDeduction(payment=p, order=o, amount=a) for o, a in feed_items])
    AdvanceDeduction.objects.bulk_create([AdvanceDeduction(payment=p, advance=a, amount=t) for a, t in adv_items])
    return p


def finalize_farmer_payment(payment, reference=""):
    if payment.status == Payment.PAID:
        return payment
    payment.status, payment.paid_at, payment.reference = Payment.PAID, timezone.now(), reference
    payment.save()
    notify(payment.farmer, "Payment sent",
           f"KES {payment.net} paid for {payment.period_start} to {payment.period_end} "
           f"(milk KES {payment.gross}, deductions KES {payment.deductions}). Ref: {reference}")
    return payment


@transaction.atomic
def apply_credit_payment(farmer, amount, method, reference="", user=None):
    remaining, applied = Decimal(amount), Decimal("0")
    for o in (CreditOrder.objects.select_for_update()
              .filter(farmer=farmer, amount_paid__lt=F("total_cost")).order_by("created")):
        if remaining <= 0:
            break
        take = min(o.balance, remaining)
        o.amount_paid += take
        o.save(update_fields=["amount_paid"])
        remaining -= take
        applied += take
    if applied <= 0:
        raise ValueError("This farmer has no feed credit to repay.")
    cp = CreditPayment.objects.create(organization=farmer.organization, farmer=farmer, amount=applied,
                                      method=method, reference=reference, recorded_by=user)
    notify(farmer, "Credit payment received",
           f"KES {applied} received ({method.title()}). Credit balance now KES {farmer.credit_balance()}. Ref: {reference}")
    return cp
