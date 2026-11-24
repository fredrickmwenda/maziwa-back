from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import allow, membership, require
from core.tenancy import TenantMixin, same_org

from .models import Animal, AnimalMilkRecord, HealthEvent
from .serializers import AnimalMilkRecordSerializer, AnimalSerializer, HealthEventSerializer
from .services import post_vet_expense


class AnimalOwnership:
    """Shared checks: an animal must be in this dairy and, for a farmer, be their own."""
    def check_animal(self, animal):
        if animal.farmer.organization_id != self.org.id:
            raise ValidationError({"animal": "Not found."})
        if self.m.role.kind == KIND_FARMER and animal.farmer_id != self.m.farmer.pk:
            raise ValidationError({"animal": "This is not your animal."})


class AnimalViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Animal.objects.select_related("farmer").prefetch_related("events")
    serializer_class = AnimalSerializer
    permission_classes = [require("herd.manage", "herd.view")]
    org_lookup = "farmer__organization"
    farmer_lookup = "farmer"

    def perform_create(self, s):
        farmer = self.m.farmer if self.m.role.kind == KIND_FARMER else s.validated_data.get("farmer")
        if farmer is None:
            raise ValidationError({"farmer": "Required."})
        same_org(farmer, self.org, "farmer")
        s.save(farmer=farmer)

    def perform_update(self, s):
        s.save(farmer=s.instance.farmer)   # an animal never moves to another farmer


class HealthEventViewSet(AnimalOwnership, TenantMixin, viewsets.ModelViewSet):
    queryset = HealthEvent.objects.select_related("animal__farmer")
    serializer_class = HealthEventSerializer
    permission_classes = [require("herd.manage", "herd.view")]
    org_lookup = "animal__farmer__organization"
    farmer_lookup = "animal__farmer"

    def _set_withdrawal(self, ev):
        ev.withdrawal_ends = ev.date + timedelta(days=ev.withdrawal_days) if ev.withdrawal_days else None
        ev.save(update_fields=["withdrawal_ends"])

    @transaction.atomic
    def perform_create(self, s):
        self.check_animal(s.validated_data["animal"])
        ev = s.save(recorded_by=self.request.user)
        self._set_withdrawal(ev)
        wants = str(self.request.data.get("post_expense", "")).lower() in ("1", "true", "yes")
        if wants and ev.cost > 0 and self.m.role.kind != KIND_FARMER and self.m.has("expenses.manage"):
            post_vet_expense(ev, self.request.user)   # only when the dairy itself paid the vet

    @transaction.atomic
    def perform_update(self, s):
        self.check_animal(s.instance.animal)
        self._set_withdrawal(s.save())


class YieldViewSet(AnimalOwnership, TenantMixin, viewsets.ModelViewSet):
    """Milk per cow."""
    queryset = AnimalMilkRecord.objects.select_related("animal__farmer")
    serializer_class = AnimalMilkRecordSerializer
    permission_classes = [require("herd.manage", "herd.view")]
    org_lookup = "animal__farmer__organization"
    farmer_lookup = "animal__farmer"

    def perform_create(self, s):
        self.check_animal(s.validated_data["animal"])
        s.save(recorded_by=self.request.user)

    @action(detail=False, methods=["get"])
    def ranking(self, request):
        """Best and worst cows over a period (default last 30 days)."""
        q, today = request.query_params, timezone.localdate()
        start, end = q.get("start") or str(today - timedelta(days=29)), q.get("end") or str(today)
        rows = (self.get_queryset().filter(date__range=(start, end))
                .values("animal_id", "animal__tag", "animal__name", "animal__farmer__full_name")
                .annotate(total=Sum("litres"), days=Count("date", distinct=True)).order_by("-total"))
        return Response([{
            "rank": i + 1, "animal": r["animal_id"], "tag": r["animal__tag"], "name": r["animal__name"],
            "farmer": r["animal__farmer__full_name"], "total": r["total"], "days": r["days"],
            "average_per_day": (r["total"] / r["days"]).quantize(Decimal("0.01")),
        } for i, r in enumerate(rows)])


def _events_in_scope(request):
    m = membership(request)
    qs = HealthEvent.objects.filter(animal__farmer__organization=m.organization).select_related("animal__farmer")
    if m.role.kind == KIND_FARMER:
        return qs.filter(animal__farmer=m.farmer)
    if request.query_params.get("farmer"):
        qs = qs.filter(animal__farmer=request.query_params["farmer"])
    return qs


@api_view(["GET"])
@permission_classes([allow("herd.view")])
def withdrawals(request):
    """Animals whose milk must not be sold right now (so the dairy does not mix it into the tank)."""
    on = request.query_params.get("date") or timezone.localdate()
    qs = _events_in_scope(request).filter(withdrawal_ends__gte=on, date__lte=on)
    return Response([{
        "animal": e.animal_id, "tag": e.animal.tag, "name": e.animal.name, "farmer": e.animal.farmer_id,
        "farmer_name": e.animal.farmer.full_name, "kind": e.get_kind_display(), "description": e.description,
        "withdrawal_ends": e.withdrawal_ends} for e in qs.order_by("withdrawal_ends")])


@api_view(["GET"])
@permission_classes([allow("herd.view")])
def due(request):
    """Vaccinations / checks due in the next 30 days (or up to a week overdue)."""
    today = timezone.localdate()
    qs = _events_in_scope(request).filter(next_due__range=(today - timedelta(days=7), today + timedelta(days=30)))
    return Response([{
        "event": e.id, "animal": e.animal_id, "tag": e.animal.tag, "farmer_name": e.animal.farmer.full_name,
        "kind": e.get_kind_display(), "description": e.description, "next_due": e.next_due,
        "overdue": e.next_due < today} for e in qs.order_by("next_due")])
