from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import membership, require
from apps.farmers.models import Farmer
from apps.mpesa.daraja import MpesaError
from apps.mpesa.services import get_org_daraja, payout_farmer_payment, start_stk
from core.documents import file_response
from core.tenancy import TenantMixin

from .documents import payment_slip_pdf
from .models import CreditPayment, Payment
from .serializers import CreditPaymentSerializer, PaymentSerializer
from .services import apply_credit_payment, finalize_farmer_payment, generate_payment


class PaymentViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.select_related("farmer")
    serializer_class = PaymentSerializer
    permission_classes = [require(None, "payments.view")]

    @action(detail=False, methods=["post"], permission_classes=[require("payments.manage")])
    def generate(self, request):
        start, end = request.data.get("start"), request.data.get("end")
        if not (start and end):
            raise ValidationError({"detail": "start and end required"})
        created = [p.id for f in Farmer.objects.filter(organization=self.org, is_active=True)
                   if (p := generate_payment(f, start, end))]
        return Response({"created": len(created), "ids": created})

    @action(detail=True, methods=["post"], permission_classes=[require("payments.manage")])
    def mark_paid(self, request, pk=None):
        """Manual confirmation (cash, bank, or an M-Pesa payment made outside the app)."""
        p = self.get_object()
        if p.status == Payment.PAID:
            raise ValidationError({"detail": "Already paid"})
        finalize_farmer_payment(p, request.data.get("reference", ""))
        return Response(PaymentSerializer(p).data)

    @action(detail=True, methods=["post"], permission_classes=[require("payments.manage")])
    def pay_mpesa(self, request, pk=None):
        try:
            tx = payout_farmer_payment(self.get_object(), request.user)
        except MpesaError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"transaction": tx.id, "message": "Sent to M-Pesa. The payment is marked paid when M-Pesa confirms."}, status=202)

    @action(detail=False, methods=["post"], permission_classes=[require("payments.manage")])
    def pay_all_mpesa(self, request):
        sent, errors = 0, []
        for p in self.get_queryset().filter(status=Payment.PENDING, net__gt=0):
            try:
                payout_farmer_payment(p, request.user)
                sent += 1
            except MpesaError as e:
                errors.append(f"{p.farmer.full_name}: {e}")
                if "not set up" in str(e) or "missing" in str(e):
                    break
        return Response({"sent": sent, "errors": errors[:10]})

    @action(detail=True, methods=["get"])
    def slip(self, request, pk=None):
        p = self.get_object()
        return file_response(payment_slip_pdf(p), "application/pdf", f"payment-{p.farmer.member_no}-{p.period_end}.pdf")


def _amount(raw):
    try:
        a = Decimal(str(raw))
    except InvalidOperation:
        raise ValidationError({"amount": "Enter a valid amount."})
    if a <= 0:
        raise ValidationError({"amount": "Amount must be above zero."})
    return a


class CreditPaymentViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CreditPayment.objects.select_related("farmer")
    serializer_class = CreditPaymentSerializer
    permission_classes = [require(None, "store.view")]


@api_view(["POST"])
@permission_classes([require()])
def credit_pay(request):
    """STK push so a farmer (or staff for them) settles feed credit from M-Pesa."""
    m = membership(request)
    org = m.organization
    if m.role.kind == KIND_FARMER:
        farmer = m.farmer
    else:
        if not m.has("credit.collect"):
            raise PermissionDenied("You do not have permission to collect credit repayments.")
        farmer = get_object_or_404(Farmer, pk=request.data.get("farmer"), organization=org)
    if farmer is None:
        raise ValidationError({"detail": "No farmer record."})
    bal = farmer.credit_balance()
    if bal <= 0:
        raise ValidationError({"detail": "No feed credit is owed."})
    amount = min(_amount(request.data.get("amount")), bal)
    try:
        tx = start_stk(get_org_daraja(org, "stk"), org=org, kind="CREDIT", phone=request.data.get("phone") or farmer.phone,
                       amount=amount, reference=farmer.member_no, desc="Feed credit", user=request.user, farmer=farmer)
    except MpesaError as e:
        raise ValidationError({"detail": str(e)})
    return Response({"transaction": tx.id, "message": "Check the phone and enter the M-Pesa PIN."}, status=202)


@api_view(["POST"])
@permission_classes([require("credit.collect")])
def credit_cash(request):
    m = membership(request)
    farmer = get_object_or_404(Farmer, pk=request.data.get("farmer"), organization=m.organization)
    try:
        cp = apply_credit_payment(farmer, min(_amount(request.data.get("amount")), farmer.credit_balance()),
                                  "CASH", request.data.get("reference", ""), user=request.user)
    except ValueError as e:
        raise ValidationError({"detail": str(e)})
    return Response(CreditPaymentSerializer(cp).data, status=201)
