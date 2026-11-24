from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import allow, membership, require
from apps.farmers.models import Farmer
from apps.mpesa.daraja import MpesaError
from apps.mpesa.services import payout_advance
from core.tenancy import TenantMixin

from .models import Advance
from .serializers import AdvanceSerializer, AdvanceSettingsSerializer
from .services import decide, get_settings, mark_disbursed, request_advance


class AdvanceViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Advance.objects.select_related("farmer")
    serializer_class = AdvanceSerializer
    permission_classes = [require(None, "advances.view")]

    @action(detail=False, methods=["post"], url_path="request", permission_classes=[require("advances.request")])
    def apply(self, request):
        """A farmer asks for an advance. Staff with advances.manage may file one for a farmer."""
        m = self.m
        if m.role.kind == KIND_FARMER:
            farmer = m.farmer
        elif m.has("advances.manage"):
            farmer = get_object_or_404(Farmer, pk=request.data.get("farmer"), organization=self.org)
        else:
            raise PermissionDenied("Only farmers can request an advance.")
        try:
            adv = request_advance(farmer, request.data.get("amount"), request.data.get("reason", ""))
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(AdvanceSerializer(adv).data, status=201)

    def _decide(self, request, approve):
        try:
            return Response(AdvanceSerializer(decide(self.get_object(), approve, request.user, request.data.get("note", ""))).data)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

    @action(detail=True, methods=["post"], permission_classes=[require("advances.manage")])
    def approve(self, request, pk=None):
        return self._decide(request, True)

    @action(detail=True, methods=["post"], permission_classes=[require("advances.manage")])
    def reject(self, request, pk=None):
        return self._decide(request, False)

    @action(detail=True, methods=["post"], permission_classes=[require("advances.manage")])
    def pay_mpesa(self, request, pk=None):
        try:
            tx = payout_advance(self.get_object(), request.user)
        except (MpesaError, ValueError) as e:
            raise ValidationError({"detail": str(e)})
        return Response({"transaction": tx.id, "message": "Sent to M-Pesa. Marked paid out when M-Pesa confirms."}, status=202)

    @action(detail=True, methods=["post"], permission_classes=[require("advances.manage")])
    def mark_paid(self, request, pk=None):
        """Cash or bank payment made outside the app."""
        try:
            adv = mark_disbursed(self.get_object(), request.data.get("method", "CASH"), request.data.get("reference", ""), request.user)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(AdvanceSerializer(adv).data)


@api_view(["GET", "PUT"])
@permission_classes([allow("advances.view")])
def advance_settings(request):
    m = membership(request)
    cfg = get_settings(m.organization)
    if request.method == "PUT":
        if not m.has("advances.manage"):
            raise PermissionDenied("You cannot change advance rules.")
        s = AdvanceSettingsSerializer(cfg, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(AdvanceSettingsSerializer(cfg).data)
