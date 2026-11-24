from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.expenses.models import Expense
from apps.farmers.models import Farmer
from apps.milk.models import MilkCollection

from .models import Route, RouteTrip, Transporter, TransporterPayment

ACCEPTED = F("litres") - F("rejected_litres")


def open_trip(org, route, day, session, user=None):
    """Get or create the route sheet for a route, day and session. Returns (trip, created)."""
    t = route.transporter
    return RouteTrip.objects.get_or_create(
        organization=org, route=route, date=day, session=session,
        defaults=dict(transporter=t, vehicle_reg=t.vehicle_reg if t else "", created_by=user))


def open_day(org, day, session, user=None):
    """Open a sheet for every active route. Returns how many were new."""
    return sum(open_trip(org, r, day, session, user)[1] for r in Route.objects.filter(organization=org, is_active=True)
               .select_related("transporter"))


def trip_lines(trip):
    """[(farmer, collection or None)]: farmers on the route plus anyone who already delivered on this sheet."""
    cols = {c.farmer_id: c for c in MilkCollection.objects
            .filter(farmer__organization=trip.organization, date=trip.date, session=trip.session)
            .filter(Q(trip=trip) | Q(farmer__route=trip.route)).select_related("farmer")}
    farmers = list(Farmer.objects.filter(organization=trip.organization, route=trip.route, is_active=True).order_by("member_no"))
    seen = {f.id for f in farmers}
    farmers += [c.farmer for fid, c in cols.items() if fid not in seen]
    return [(f, cols.get(f.id)) for f in farmers]


@transaction.atomic
def receive_trip(trip, litres, temperature, notes, user):
    """The centre measured the milk. Closes the sheet."""
    trip = RouteTrip.objects.select_for_update().get(pk=trip.pk)
    if trip.status != RouteTrip.OPEN:
        raise ValueError("This route sheet has already been received.")
    if litres < 0:
        raise ValueError("Litres cannot be negative.")
    trip.received_litres, trip.temperature, trip.notes = litres, temperature, (notes or "")[:200]
    trip.status, trip.received_at, trip.received_by = RouteTrip.RECEIVED, timezone.now(), user
    trip.save()
    return trip


def transporter_due(org, start, end):
    """{transporter_id: {"litres", "trips"}} for accepted milk carried in the period."""
    rows = (MilkCollection.objects.filter(organization=org, trip__transporter__isnull=False, trip__date__range=(start, end))
            .values("trip__transporter").annotate(litres=Sum(ACCEPTED), trips=Count("trip", distinct=True)))
    return {r["trip__transporter"]: {"litres": r["litres"] or Decimal("0"), "trips": r["trips"]} for r in rows}


@transaction.atomic
def pay_transporter(transporter, start, end, reference, user):
    """Record what a transporter is owed for a period as paid, and post it to Expenses (Transport)."""
    if TransporterPayment.objects.filter(transporter=transporter, period_start__lte=end, period_end__gte=start).exists():
        raise ValueError("This transporter has already been paid for part of this period.")
    litres = transporter_due(transporter.organization, start, end).get(transporter.id, {}).get("litres", Decimal("0"))
    amount = (litres * transporter.rate_per_litre).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Nothing is due. Check the rate per litre and the period.")
    expense = Expense.objects.create(
        organization=transporter.organization, category="TRANSPORT", amount=amount, date=timezone.localdate(),
        description=f"Transport {transporter.name}, {start} to {end} ({litres} L)", paid_to=transporter.name,
        reference=reference, recorded_by=user)
    return TransporterPayment.objects.create(
        organization=transporter.organization, transporter=transporter, period_start=start, period_end=end,
        litres=litres, rate=transporter.rate_per_litre, amount=amount, reference=reference, expense=expense, paid_by=user)
