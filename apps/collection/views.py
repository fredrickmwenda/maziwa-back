from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import require
from apps.farmers.models import Farmer
from apps.milk.models import MilkCollection
from apps.milk.serializers import MilkCollectionSerializer
from apps.milk.services import notify_collection
from core.documents import file_response
from core.tenancy import TenantMixin, same_org

from .documents import route_sheet_pdf
from .models import CollectionCentre, Route, RouteTrip, Transporter, TransporterPayment
from .serializers import (CentreSerializer, RouteSerializer, RouteTripSerializer, TransporterPaymentSerializer,
                          TransporterSerializer)
from .services import open_day, open_trip, pay_transporter, receive_trip, transporter_due, trip_lines

READ_WRITE = [require("routes.manage", "routes.view")]


def _day(value, field="date"):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError({field: "Use a date like 2026-11-30."})


def _unique_name(model, org, name, exclude=None):
    qs = model.objects.filter(organization=org, name__iexact=name)
    if exclude:
        qs = qs.exclude(pk=exclude.pk)
    if qs.exists():
        raise ValidationError({"name": "This name is already used."})


class NamedMixin:
    """Names are unique per dairy."""
    model = None

    def perform_create(self, s):
        _unique_name(self.model, self.org, s.validated_data["name"])
        s.save(organization=self.org)

    def perform_update(self, s):
        if "name" in s.validated_data:
            _unique_name(self.model, self.org, s.validated_data["name"], s.instance)
        s.save()


class CentreViewSet(NamedMixin, TenantMixin, viewsets.ModelViewSet):
    model = CollectionCentre
    queryset = CollectionCentre.objects.all()
    serializer_class = CentreSerializer
    permission_classes = READ_WRITE
    farmer_lookup = None


class TransporterViewSet(NamedMixin, TenantMixin, viewsets.ModelViewSet):
    model = Transporter
    queryset = Transporter.objects.all()
    serializer_class = TransporterSerializer
    permission_classes = READ_WRITE
    farmer_lookup = None

    @action(detail=False, methods=["get"])
    def due(self, request):
        """What each transporter is owed for a period (accepted litres carried x rate per litre)."""
        q = request.query_params
        today = timezone.localdate()
        start, end = _day(q.get("start") or str(today.replace(day=1)), "start"), _day(q.get("end") or str(today), "end")
        carried = transporter_due(self.org, start, end)
        paid = set(TransporterPayment.objects.filter(organization=self.org, period_start__lte=end, period_end__gte=start)
                   .values_list("transporter_id", flat=True))
        return Response([{
            "id": t.id, "name": t.name, "vehicle_reg": t.vehicle_reg, "rate_per_litre": t.rate_per_litre,
            "trips": carried.get(t.id, {}).get("trips", 0), "litres": carried.get(t.id, {}).get("litres", Decimal("0")),
            "amount": (carried.get(t.id, {}).get("litres", Decimal("0")) * t.rate_per_litre).quantize(Decimal("0.01")),
            "already_paid": t.id in paid} for t in self.get_queryset().filter(is_active=True)])

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """{"start": "...", "end": "...", "reference": "M-Pesa code"}: records the payment and posts a Transport expense."""
        d = request.data
        try:
            p = pay_transporter(self.get_object(), _day(d.get("start"), "start"), _day(d.get("end"), "end"), str(d.get("reference", "")), request.user)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(TransporterPaymentSerializer(p).data, status=201)


class TransporterPaymentViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = TransporterPayment.objects.select_related("transporter")
    serializer_class = TransporterPaymentSerializer
    permission_classes = READ_WRITE
    farmer_lookup = None


class RouteViewSet(NamedMixin, TenantMixin, viewsets.ModelViewSet):
    model = Route
    queryset = Route.objects.select_related("centre", "transporter").annotate(n_farmers=Count("farmers"))
    serializer_class = RouteSerializer
    permission_classes = READ_WRITE
    farmer_lookup = None

    def _check_links(self, s):
        for field in ("centre", "transporter"):
            if s.validated_data.get(field):
                same_org(s.validated_data[field], self.org, field)

    def perform_create(self, s):
        self._check_links(s)
        super().perform_create(s)

    def perform_update(self, s):
        self._check_links(s)
        super().perform_update(s)


class RouteTripViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    """Route sheets."""
    queryset = (RouteTrip.objects.select_related("route__centre", "transporter")
                .annotate(delivered=Sum("collections__litres"), rejected=Sum("collections__rejected_litres"), farmers_n=Count("collections")))
    serializer_class = RouteTripSerializer
    permission_classes = READ_WRITE
    farmer_lookup = None

    def get_queryset(self):
        qs, q = super().get_queryset(), self.request.query_params
        for key in ("date", "session", "route", "status"):
            if q.get(key):
                qs = qs.filter(**{key: q[key]})
        return qs

    def _out(self, trip):
        return Response(RouteTripSerializer(self.get_queryset().get(pk=trip.pk)).data)

    def create(self, request, *args, **kwargs):
        d = request.data
        route = get_object_or_404(Route, pk=d.get("route"), organization=self.org)
        if d.get("session") not in ("AM", "PM"):
            raise ValidationError({"session": "Choose morning or evening."})
        trip, created = open_trip(self.org, route, _day(d.get("date")), d["session"], request.user)
        resp = self._out(trip)
        resp.status_code = 201 if created else 200
        return resp

    @action(detail=False, methods=["post"])
    def open_day(self, request):
        """Open a sheet for every active route: {"date": "2026-11-30", "session": "AM"}."""
        d = request.data
        if d.get("session") not in ("AM", "PM"):
            raise ValidationError({"session": "Choose morning or evening."})
        return Response({"opened": open_day(self.org, _day(d.get("date")), d["session"], request.user)})

    @action(detail=True, methods=["get"])
    def lines(self, request, pk=None):
        """The farmers on this sheet, with any litres already recorded."""
        trip = self.get_object()
        return Response([{
            "farmer": f.id, "member_no": f.member_no, "name": f.full_name, "phone": f.phone, "on_route": f.route_id == trip.route_id,
            "collection": None if c is None else {
                "id": c.id, "litres": c.litres, "fat_percent": c.fat_percent, "protein_percent": c.protein_percent,
                "alcohol_passed": c.alcohol_passed, "rejected_litres": c.rejected_litres, "reject_reason": c.reject_reason}}
            for f, c in trip_lines(trip)])

    @action(detail=True, methods=["post"], permission_classes=[require("milk.record", "routes.view")])
    def record(self, request, pk=None):
        """Save the litres written on the sheet: {"rows": [{"farmer": 3, "litres": 12.5, "fat_percent": 3.8, ...}]}."""
        trip = self.get_object()
        if trip.status != RouteTrip.OPEN:
            raise ValidationError({"detail": "This route sheet has already been received, so it cannot be changed."})
        saved = 0
        for row in request.data.get("rows") or []:
            row = {k: v for k, v in row.items() if v not in ("", None)}
            if "litres" not in row:
                continue
            farmer = get_object_or_404(Farmer, pk=row.get("farmer"), organization=self.org)
            existing = MilkCollection.objects.filter(farmer=farmer, date=trip.date, session=trip.session).first()
            s = MilkCollectionSerializer(existing, data={**row, "farmer": farmer.pk, "date": trip.date, "session": trip.session},
                                         partial=existing is not None, context={"org": self.org})
            s.is_valid(raise_exception=True)
            c = s.save(organization=self.org, recorded_by=request.user, trip=trip, route=trip.route, centre=trip.route.centre)
            if existing is None:
                notify_collection(c)
            saved += 1
        return Response({"saved": saved})

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """The centre measured the milk: {"received_litres": 410, "temperature": 5.2, "notes": ""}."""
        d = request.data
        try:
            litres = Decimal(str(d.get("received_litres")))
            temp = Decimal(str(d["temperature"])) if d.get("temperature") not in (None, "") else None
        except InvalidOperation:
            raise ValidationError({"detail": "Enter the litres (and temperature) as numbers."})
        try:
            trip = receive_trip(self.get_object(), litres, temp, d.get("notes", ""), request.user)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return self._out(trip)

    @action(detail=True, methods=["get"])
    def sheet(self, request, pk=None):
        trip = self.get_object()
        return file_response(route_sheet_pdf(trip, trip_lines(trip)), "application/pdf",
                             f"route-sheet-{trip.route.name}-{trip.date}-{trip.session}.pdf")
