"""Quality-based pricing."""
from decimal import Decimal

from apps.notifications.services import notify

from .models import QualityTier


def load_tiers(org):
    """{"FAT": [(min, bonus), ...], "PROTEIN": [...]} sorted ascending, loaded once per request."""
    tiers = {QualityTier.FAT: [], QualityTier.PROTEIN: []}
    for t in QualityTier.objects.filter(organization=org):
        tiers[t.metric].append((t.min_value, t.bonus_per_litre))
    for rows in tiers.values():
        rows.sort()
    return tiers


def bonus_rate(tiers, fat, protein):
    """KES per litre added to (or taken from) the base price: highest fat tier reached + highest protein tier reached."""
    total = Decimal("0")
    for metric, value in ((QualityTier.FAT, fat), (QualityTier.PROTEIN, protein)):
        if value is None:
            continue
        hit = None
        for floor, bonus in tiers[metric]:
            if value >= floor:
                hit = bonus
        if hit is not None:
            total += hit
    return total


def notify_collection(c):
    """Tell the farmer what was accepted and, if anything, what was rejected."""
    notify(c.farmer, "Milk received", f"{c.accepted_litres} L accepted on {c.date} ({c.get_session_display()}).")
    if c.rejected_litres > 0:
        notify(c.farmer, "Milk rejected",
               f"{c.rejected_litres} L of your {c.date} delivery was rejected: {c.get_reject_reason_display()}. It is not paid for.")
